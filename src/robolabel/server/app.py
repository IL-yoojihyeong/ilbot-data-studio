"""IL-BOT Data Studio API server (패키지명은 robolabel 유지).

    uvicorn robolabel.server.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import exporter, importer, lerobot
from .db import (DATA_DIR, Dataset, Episode, ExportTask, ImportTask, LabelJob,
                 Project, Segment, TrainingDataset, User, init_db, get_session)

app = FastAPI(title="IL-BOT Data Studio")
init_db()

# Optional HTTP Basic Auth for exposing the server beyond the local network.
# Enabled by setting ROBOLABEL_PASSWORD (and optionally ROBOLABEL_USER).
AUTH_USER = os.environ.get("ROBOLABEL_USER", "admin")
AUTH_PASSWORD = os.environ.get("ROBOLABEL_PASSWORD")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if AUTH_PASSWORD:
        import base64
        import secrets
        ok = False
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
                ok = (secrets.compare_digest(user, AUTH_USER)
                      and secrets.compare_digest(pw, AUTH_PASSWORD))
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="IL-BOT Data Studio"'})
    return await call_next(request)


def db():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


# ------------------------------------------------------------------ schemas
ROBOT_TYPES = ["G2", "G2_Omnihand2025", "G2_Omnipicker2025",
               "X2_Omnihand2025", "X2_Omnipicker2025"]
PROJECT_USAGES = ["Testing", "Formal", "R&D"]
PROJECT_DIFFICULTIES = ["easy", "middle", "high"]


class UserIn(BaseModel):
    name: str
    role: str = "labeler"                   # admin | labeler | reviewer


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    usage: str = ""                         # Testing | Formal | R&D
    difficulty: str = ""                    # easy | middle | high
    action: str = ""                        # Action 정의 (텍스트)
    owner_id: int | None = None
    member_ids: list[int] | None = None
    start_date: str = ""
    due_date: str = ""
    status: str = "active"                  # active | completed | archived
    tags: list[str] = []
    robot_model: str = ""                   # one of ROBOT_TYPES


class JobIn(BaseModel):
    name: str
    description: str = ""
    canonical_instruction: str = ""
    difficulty: str = ""                    # easy | medium | hard
    object: str = ""
    target: str = ""
    environment: str = ""
    success_criteria: str = ""
    target_episodes: int = 0
    assignee_id: int | None = None


class ImportIn(BaseModel):
    """Every episode must belong to a Job: an import either creates one
    (job) or targets an existing one (job_id)."""
    path: str
    job: JobIn | None = None
    job_id: int | None = None


class SegmentIn(BaseModel):
    start_frame: int
    end_frame: int
    text: str = ""
    skill: str = ""


class LabelsIn(BaseModel):
    pass_status: str | None = None          # pass | non_pass | unlabeled
    failure_reason: str | None = None
    task_text: str | None = None
    segments: list[SegmentIn] | None = None
    job_id: int | None = None
    recorder_id: int | None = None
    recorded_at: str | None = None
    robot_serial: str | None = None


class ReviewIn(BaseModel):
    action: str                             # submit | accept | reject | reopen
    user_id: int | None = None              # acting profile (reviewer on accept/reject)
    note: str = ""


class TrainingDatasetIn(BaseModel):
    """SPEC 2단계 Dataset: job pool + filters + split config."""
    name: str
    description: str = ""
    job_ids: list[int] = []
    review_filter: str = "done"             # done | any
    include_non_pass: bool = False
    ratios: dict[str, float] = {"train": 80, "val": 10, "test": 10}
    seed: int = 42
    job_splits: dict[str, str] = {}         # str(job_id) -> train | val | test


# ----------------------------------------------------------------- helpers
def user_json(u: User) -> dict:
    return {"id": u.id, "name": u.name, "role": u.role}


def project_json(p: Project) -> dict:
    eps = [e for d in p.datasets for e in d.episodes]
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "usage": p.usage, "difficulty": p.difficulty, "action": p.action,
        "owner_id": p.owner_id, "owner": p.owner.name if p.owner else None,
        "members": [user_json(u) for u in p.members],
        "start_date": p.start_date, "due_date": p.due_date,
        "status": p.status, "tags": p.tags or [],
        "robot_model": p.robot_model,
        "datasets": len(p.datasets), "jobs": len(p.jobs),
        "episodes": len(eps),
        "labeled": sum(1 for e in eps if e.review_status != "unlabeled"),
        "done": sum(1 for e in eps if e.review_status == "done"),
        "created_at": p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
    }


def job_json(j: LabelJob) -> dict:
    return {
        "id": j.id, "name": j.name, "description": j.description,
        "canonical_instruction": j.canonical_instruction,
        "difficulty": j.difficulty, "object": j.object_name,
        "target": j.target_name, "environment": j.environment,
        "success_criteria": j.success_criteria,
        "target_episodes": j.target_episodes,
        "assignee_id": j.assignee_id,
        "assignee": j.assignee.name if j.assignee else None,
        "episodes": len(j.episodes),
        "done": sum(1 for e in j.episodes if e.review_status == "done"),
    }


def ep_json(e: Episode) -> dict:
    features = (e.dataset.info or {}).get("features", {})
    cameras = {k: f.get("shape") for k, f in features.items()
               if f.get("dtype") == "video"}
    return {
        "id": e.id, "dataset_id": e.dataset_id, "job_id": e.job_id,
        "project_id": e.dataset.project_id,
        "project": e.dataset.project.name if e.dataset.project else None,
        "episode_index": e.episode_index, "length": e.length,
        "fps": e.dataset.fps, "videos": e.videos, "cameras": cameras,
        "task_text": e.task_text, "pass_status": e.pass_status,
        "failure_reason": e.failure_reason,
        "recorder_id": e.recorder_id,
        "recorder": e.recorder.name if e.recorder else None,
        "recorded_at": e.recorded_at,
        "robot_model": e.dataset.robot_type, "robot_serial": e.robot_serial,
        "review_status": e.review_status,
        "reviewer": e.reviewer.name if e.reviewer else None,
        "review_note": e.review_note,
        "source_path": e.source_path,
        "segments": [{"id": sg.id, "start_frame": sg.start_frame,
                      "end_frame": sg.end_frame, "text": sg.text,
                      "skill": sg.skill} for sg in e.segments],
    }


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


# ------------------------------------------------------------------- users
@app.get("/api/users")
def list_users(s: Session = Depends(db)):
    return [user_json(u) for u in s.scalars(select(User).order_by(User.name))]


@app.post("/api/users")
def create_user(body: UserIn, s: Session = Depends(db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "이름이 비어 있습니다")
    if s.scalar(select(User).where(User.name == name)):
        raise HTTPException(400, f"이미 존재하는 이름: {name}")
    u = User(name=name, role=body.role)
    s.add(u)
    s.commit()
    return user_json(u)


@app.delete("/api/users/{uid}")
def delete_user(uid: int, s: Session = Depends(db)):
    u = s.get(User, uid) or _404("user")
    # null out every reference, then drop the profile
    for p in s.scalars(select(Project).where(Project.owner_id == uid)):
        p.owner_id = None
    for p in s.scalars(select(Project)):
        if u in p.members:
            p.members.remove(u)
    for j in s.scalars(select(LabelJob).where(LabelJob.assignee_id == uid)):
        j.assignee_id = None
    for e in s.scalars(select(Episode).where(Episode.recorder_id == uid)):
        e.recorder_id = None
    for e in s.scalars(select(Episode).where(Episode.reviewer_id == uid)):
        e.reviewer_id = None
    s.delete(u)
    s.commit()
    return {"ok": True}


# --------------------------------------------------------------- dashboard
@app.get("/api/dashboard")
def dashboard(project_id: int | None = None, s: Session = Depends(db)):
    projects = ([s.get(Project, project_id)] if project_id
                else list(s.scalars(select(Project))))
    projects = [p for p in projects if p]
    jobs = [j for p in projects for j in p.jobs]
    datasets = [d for p in projects for d in p.datasets]
    eps = [e for d in datasets for e in d.episodes]

    def n(st):
        return sum(1 for e in eps if e.review_status == st)

    hours = sum(e.length / (e.dataset.fps or 30) for e in eps) / 3600
    labeled = sum(1 for e in eps if e.pass_status != "unlabeled")
    passed = sum(1 for e in eps if e.pass_status == "pass")
    rejected, done = n("rejected"), n("done")

    rank = {}
    for e in eps:
        who = e.recorder.name if e.recorder else "(recorder 미지정)"
        r = rank.setdefault(who, {"recorder": who, "collected": 0, "passed": 0})
        r["collected"] += 1
        r["passed"] += e.pass_status == "pass"
    for r in rank.values():
        r["pass_rate"] = round(r["passed"] / r["collected"] * 100) if r["collected"] else 0

    trend = {}
    for e in eps:
        day = e.recorded_at or (e.dataset.created_at.strftime("%Y-%m-%d")
                                if e.dataset.created_at else "")
        if day:
            trend[day] = trend.get(day, 0) + 1

    return {
        "core": {
            "projects": len(projects), "jobs": len(jobs),
            "episodes": len(eps), "frames": sum(e.length for e in eps),
            "hours": round(hours, 2),
            "robots": len({p.robot_model for p in projects if p.robot_model}),
        },
        "efficiency": {
            "pass_rate": round(passed / labeled * 100, 1) if labeled else 0,
            "review_pass_rate": round(done / (done + rejected) * 100, 1)
                                if done + rejected else 0,
            "done_rate": round(done / len(eps) * 100, 1) if eps else 0,
        },
        "backlog": {
            "recorders": sum(1 for r in rank.values() if r["recorder"] != "(recorder 미지정)"),
            "pending_review": n("labeled"),
            "rejected": rejected,
        },
        "job_progress": [{
            "job": j.name, "collected": len(j.episodes),
            "target": j.target_episodes,
            "done": sum(1 for e in j.episodes if e.review_status == "done"),
        } for j in jobs],
        "recorder_rank": sorted(rank.values(), key=lambda r: -r["collected"]),
        "trend": [{"date": d, "count": c} for d, c in sorted(trend.items())],
    }


# ---------------------------------------------------------------- projects
def _apply_project(p: Project, body: ProjectIn, s: Session):
    if body.usage and body.usage not in PROJECT_USAGES:
        raise HTTPException(400, f"usage는 {'/'.join(PROJECT_USAGES)} 중 하나여야 합니다")
    if body.difficulty and body.difficulty not in PROJECT_DIFFICULTIES:
        raise HTTPException(400, f"difficulty는 {'/'.join(PROJECT_DIFFICULTIES)} 중 하나여야 합니다")
    robot = body.robot_model.strip()
    # allowed list, or keep a legacy value already stored on this project
    if robot and robot not in ROBOT_TYPES and robot != p.robot_model:
        raise HTTPException(400, f"로봇 Type은 {', '.join(ROBOT_TYPES)} 중 하나여야 합니다")
    p.name, p.description = body.name, body.description
    p.usage, p.difficulty, p.action = body.usage, body.difficulty, body.action
    p.owner_id = body.owner_id
    p.start_date, p.due_date = body.start_date, body.due_date
    p.status = body.status
    p.tags = [t.strip() for t in body.tags if t.strip()]
    p.robot_model = robot
    if body.member_ids is not None:
        p.members = list(s.scalars(select(User).where(User.id.in_(body.member_ids))))


@app.get("/api/projects")
def list_projects(s: Session = Depends(db)):
    return [project_json(p) for p in s.scalars(select(Project).order_by(Project.id))]


@app.get("/api/projects/{pid}")
def get_project(pid: int, s: Session = Depends(db)):
    p = s.get(Project, pid) or _404("project")
    return project_json(p)


@app.post("/api/projects")
def create_project(body: ProjectIn, s: Session = Depends(db)):
    p = Project()
    _apply_project(p, body, s)
    s.add(p)
    s.commit()
    return {"id": p.id}


@app.patch("/api/projects/{pid}")
def update_project(pid: int, body: ProjectIn, s: Session = Depends(db)):
    p = s.get(Project, pid) or _404("project")
    _apply_project(p, body, s)
    s.commit()
    return project_json(p)


@app.delete("/api/projects/{pid}")
def delete_project(pid: int, s: Session = Depends(db)):
    p = s.get(Project, pid) or _404("project")
    s.delete(p)
    s.commit()
    return {"ok": True}


# -------------------------------------------------------------------- jobs
def _apply_job(j: LabelJob, body: JobIn):
    j.name, j.description = body.name, body.description
    j.canonical_instruction = body.canonical_instruction
    j.difficulty = body.difficulty
    j.object_name, j.target_name = body.object, body.target
    j.environment = body.environment
    j.success_criteria = body.success_criteria
    j.target_episodes = max(0, body.target_episodes)
    j.assignee_id = body.assignee_id


@app.get("/api/projects/{pid}/jobs")
def list_jobs(pid: int, s: Session = Depends(db)):
    jobs = s.scalars(select(LabelJob).where(LabelJob.project_id == pid)
                     .order_by(LabelJob.id))
    return [job_json(j) for j in jobs]


@app.post("/api/projects/{pid}/jobs")
def create_job(pid: int, body: JobIn, s: Session = Depends(db)):
    s.get(Project, pid) or _404("project")
    j = LabelJob(project_id=pid)
    _apply_job(j, body)
    s.add(j)
    s.commit()
    return {"id": j.id}


@app.patch("/api/jobs/{jid}")
def update_job(jid: int, body: JobIn, s: Session = Depends(db)):
    j = s.get(LabelJob, jid) or _404("job")
    _apply_job(j, body)
    s.commit()
    return job_json(j)


@app.delete("/api/jobs/{jid}")
def delete_job(jid: int, s: Session = Depends(db)):
    j = s.get(LabelJob, jid) or _404("job")
    # every episode must belong to a job — no orphaning via job deletion
    if j.episodes:
        raise HTTPException(
            409, f"에피소드 {len(j.episodes)}개가 속해 있어 삭제할 수 없습니다. "
                 "에피소드를 다른 Job으로 옮긴 뒤 삭제하세요.")
    s.delete(j)
    s.commit()
    return {"ok": True}


# ----------------------------------------------------------------- imports
@app.post("/api/projects/{pid}/imports")
def create_import(pid: int, body: ImportIn, s: Session = Depends(db)):
    s.get(Project, pid) or _404("project")
    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(400, f"path does not exist: {path}")
    try:
        fmt = importer.detect_format(path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # every episode belongs to a job: create one per import (default flow),
    # or attach to an existing one
    if body.job is not None:
        if not body.job.name.strip():
            raise HTTPException(400, "Job 이름을 입력하세요")
        j = LabelJob(project_id=pid)
        _apply_job(j, body.job)
        s.add(j)
        s.flush()
        job_id = j.id
    elif body.job_id is not None:
        j = s.get(LabelJob, body.job_id) or _404("job")
        if j.project_id != pid:
            raise HTTPException(400, "다른 프로젝트의 Job입니다")
        job_id = j.id
    else:
        raise HTTPException(400, "모든 에피소드는 Job에 속해야 합니다 — Job 정보를 입력하세요")

    t = ImportTask(project_id=pid, job_id=job_id, path=str(path),
                   source_format=fmt)
    s.add(t)
    s.commit()
    importer.start_import(t.id)
    return {"id": t.id, "format": fmt, "job_id": job_id}


# 수집기(브리지) 직접 업로드: 에피소드 폴더를 tar(.gz) 스트림으로 받아
# ROBOLABEL_DATA/raw/<uuid>에 풀고 기존 import 파이프라인으로 연결한다.
# SFTP 전송을 대체하는 경로 — Docker/외부 배포에서 서버는 HTTP만 노출하면 된다.
@app.post("/api/jobs/{jid}/episodes")
async def upload_episode(jid: int, uuid: str, request: Request,
                         s: Session = Depends(db)):
    j = s.get(LabelJob, jid) or _404("job")
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{3,120}", uuid):
        raise HTTPException(400, "uuid 형식이 올바르지 않습니다")
    dest = DATA_DIR / "raw" / uuid
    if dest.exists():
        raise HTTPException(409, f"이미 존재하는 에피소드: raw/{uuid}")

    # 본문을 임시 파일로 스트리밍 수신 후 tar 검증·추출 (메모리 상주 없음)
    dest.parent.mkdir(parents=True, exist_ok=True)
    files: dict[str, int] = {}
    with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".tar.part") as tmp:
        async for chunk in request.stream():
            tmp.write(chunk)
        tmp.flush()
        try:
            with tarfile.open(tmp.name, mode="r:*") as tar:
                members = []
                for m in tar.getmembers():
                    name = m.name.lstrip("./")
                    if (not name or name.startswith(("/", ".."))
                            or ".." in Path(name).parts):
                        raise HTTPException(400, f"불허 경로: {m.name}")
                    if not (m.isfile() or m.isdir()):
                        continue                    # symlink/device 등 무시
                    m.name = name
                    members.append(m)
                    if m.isfile():
                        files[name] = m.size
                tar.extractall(dest, members=members)
        except tarfile.TarError as e:
            shutil.rmtree(dest, ignore_errors=True)
            raise HTTPException(400, f"tar 스트림이 아닙니다: {e}")
        except HTTPException:
            shutil.rmtree(dest, ignore_errors=True)
            raise
    if not files:
        shutil.rmtree(dest, ignore_errors=True)
        raise HTTPException(400, "빈 아카이브입니다")

    try:
        fmt = importer.detect_format(dest)
    except ValueError as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise HTTPException(400, f"에피소드 포맷 인식 실패: {e}")

    t = ImportTask(project_id=j.project_id, job_id=jid, path=str(dest),
                   source_format=fmt)
    s.add(t)
    s.commit()
    importer.start_import(t.id)
    return {"import_id": t.id, "project_id": j.project_id, "job_id": jid,
            "format": fmt, "files": files}


@app.get("/api/projects/{pid}/imports")
def list_imports(pid: int, s: Session = Depends(db)):
    ts = s.scalars(select(ImportTask).where(ImportTask.project_id == pid)
                   .order_by(ImportTask.id.desc()))
    return [{"id": t.id, "path": t.path, "format": t.source_format,
             "status": t.status, "progress": t.progress,
             "dataset_id": t.dataset_id} for t in ts]


# ---------------------------------------------------------------- episodes
@app.get("/api/projects/{pid}/episodes")
def list_episodes(pid: int, job_id: int | None = None,
                  pass_status: str | None = None,
                  review_status: str | None = None, s: Session = Depends(db)):
    q = (select(Episode).join(Dataset).where(Dataset.project_id == pid)
         .order_by(Episode.dataset_id, Episode.episode_index))
    if job_id is not None:
        q = q.where(Episode.job_id == job_id)
    if pass_status:
        q = q.where(Episode.pass_status == pass_status)
    if review_status:
        q = q.where(Episode.review_status == review_status)
    return [ep_json(e) for e in s.scalars(q)]


@app.get("/api/episodes/{eid}")
def get_episode(eid: int, s: Session = Depends(db)):
    e = s.get(Episode, eid) or _404("episode")
    return ep_json(e)


@app.get("/api/episodes/{eid}/timeseries")
def episode_timeseries(eid: int, s: Session = Depends(db)):
    e = s.get(Episode, eid) or _404("episode")
    return lerobot.read_timeseries(Path(e.dataset.root), e.data_file,
                                   e.episode_index)


@app.put("/api/episodes/{eid}/labels")
def put_labels(eid: int, body: LabelsIn, s: Session = Depends(db)):
    e = s.get(Episode, eid) or _404("episode")
    if e.review_status == "done":
        raise HTTPException(409, "done 상태에서는 수정할 수 없습니다 (reopen 후 수정)")
    if body.pass_status is not None:
        if body.pass_status not in ("pass", "non_pass", "unlabeled"):
            raise HTTPException(400, "pass_status must be pass|non_pass|unlabeled")
        e.pass_status = body.pass_status
    if body.failure_reason is not None:
        e.failure_reason = body.failure_reason
    if body.task_text is not None:
        e.task_text = body.task_text
    if body.job_id is not None:
        # every episode must belong to a job — reassign only, no clearing
        if not body.job_id:
            raise HTTPException(400, "모든 에피소드는 Job에 속해야 합니다")
        j = s.get(LabelJob, body.job_id) or _404("job")
        if j.project_id != e.dataset.project_id:
            raise HTTPException(400, "다른 프로젝트의 Job입니다")
        e.job_id = j.id
    if body.recorder_id is not None:
        e.recorder_id = body.recorder_id or None
    if body.recorded_at is not None:
        e.recorded_at = body.recorded_at
    if body.robot_serial is not None:
        e.robot_serial = body.robot_serial
    if body.segments is not None:
        for sg in list(e.segments):
            s.delete(sg)
        for sg in body.segments:
            if sg.end_frame <= sg.start_frame:
                raise HTTPException(400, "segment end_frame must be > start_frame")
            s.add(Segment(episode_id=e.id, start_frame=sg.start_frame,
                          end_frame=sg.end_frame, text=sg.text, skill=sg.skill))
    s.commit()
    s.refresh(e)
    return ep_json(e)


# unlabeled --submit--> labeled --accept--> done (view-only, reopen to undo)
#     ^                    |
#     |                    +----reject----> rejected --(relabel+submit)--> labeled
@app.post("/api/episodes/{eid}/review")
def review_episode(eid: int, body: ReviewIn, s: Session = Depends(db)):
    e = s.get(Episode, eid) or _404("episode")

    def _need(*states):
        if e.review_status not in states:
            raise HTTPException(
                409, f"'{e.review_status}' 상태에서는 {body.action} 불가")

    if body.action == "submit":
        _need("unlabeled", "rejected")
        e.review_status = "labeled"
        e.review_note = ""
    elif body.action == "accept":
        _need("labeled")
        e.review_status = "done"
        e.reviewer_id = body.user_id
        e.review_note = ""
    elif body.action == "reject":
        _need("labeled")
        e.review_status = "rejected"
        e.reviewer_id = body.user_id
        e.review_note = body.note
    elif body.action == "reopen":
        _need("done")
        e.review_status = "labeled"
    else:
        raise HTTPException(400, "action must be submit|accept|reject|reopen")
    s.commit()
    return ep_json(e)


# ------------------------------------------------------------------- video
@app.get("/api/episodes/{eid}/video/{video_key}")
def episode_video(eid: int, video_key: str, request: Request,
                  s: Session = Depends(db)):
    e = s.get(Episode, eid) or _404("episode")
    v = e.videos.get(video_key) or _404("video key")
    path = Path(e.dataset.root) / v["rel_path"]
    if not path.exists():
        _404("video file")
    return _range_response(path, request)


def _range_response(path: Path, request: Request) -> Response:
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type="video/mp4")
    unit, _, rng = range_header.partition("=")
    start_s, _, end_s = rng.partition("-")
    start = int(start_s) if start_s else 0
    end = min(int(end_s) if end_s else size - 1, size - 1)
    if unit != "bytes" or start > end:
        raise HTTPException(416, "invalid range")
    chunk = 1 << 20

    def body():
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                data = f.read(min(chunk, left))
                if not data:
                    break
                left -= len(data)
                yield data

    from fastapi.responses import StreamingResponse
    return StreamingResponse(body(), status_code=206, media_type="video/mp4",
                             headers={
                                 "Content-Range": f"bytes {start}-{end}/{size}",
                                 "Accept-Ranges": "bytes",
                                 "Content-Length": str(end - start + 1),
                             })


# ------------------------------------------------------------------ export
@app.post("/api/datasets/{did}/export")
def export_dataset(did: int, s: Session = Depends(db)):
    d = s.get(Dataset, did) or _404("dataset")
    eps = [{
        "episode_index": e.episode_index,
        "task_text": e.task_text,
        "pass_status": e.pass_status,
        "segments": [{"start_frame": sg.start_frame, "end_frame": sg.end_frame,
                      "text": sg.text, "skill": sg.skill} for sg in e.segments],
    } for e in d.episodes]
    lerobot.export_labels(Path(d.root), eps)
    return {"ok": True, "episodes": len(eps), "root": d.root}


@app.get("/api/projects/{pid}/datasets")
def list_datasets(pid: int, s: Session = Depends(db)):
    ds = s.scalars(select(Dataset).where(Dataset.project_id == pid)
                   .order_by(Dataset.id))
    return [{"id": d.id, "name": d.name, "root": d.root,
             "source_format": d.source_format, "fps": d.fps,
             "robot_type": d.robot_type, "episodes": len(d.episodes)}
            for d in ds]


# ------------------------------------- training datasets (스플릿 구성/Export)
def _resolve_counts(s: Session, t: TrainingDataset) -> dict:
    """Split counts + warnings for list/detail views; robot mix → warning."""
    try:
        res = exporter.resolve(s, t)
        return {"counts": {sp: len(res["splits"][sp]) for sp in exporter.SPLITS},
                "warnings": res["warnings"]}
    except ValueError as e:
        return {"counts": {sp: 0 for sp in exporter.SPLITS}, "warnings": [str(e)]}


def export_json(x: ExportTask) -> dict:
    return {"id": x.id, "status": x.status, "progress": x.progress,
            "out_path": x.out_path, "config": x.config or {},
            "created_at": x.created_at.strftime("%Y-%m-%d %H:%M")
                          if x.created_at else ""}


def tds_json(s: Session, t: TrainingDataset) -> dict:
    jobs = [s.get(LabelJob, jid) for jid in t.job_ids or []]
    last = t.exports[-1] if t.exports else None
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "job_ids": t.job_ids or [],
        "jobs": [{"id": j.id, "name": j.name, "project_id": j.project_id,
                  "project": j.project.name} for j in jobs if j],
        "review_filter": t.review_filter,
        "include_non_pass": t.include_non_pass,
        "ratios": t.ratios or exporter.DEFAULT_RATIOS,
        "seed": t.seed, "job_splits": t.job_splits or {},
        "robot_models": sorted({j.project.robot_model for j in jobs
                                if j and j.project.robot_model}),
        "last_export": export_json(last) if last else None,
        "created_at": t.created_at.strftime("%Y-%m-%d") if t.created_at else "",
        **_resolve_counts(s, t),
    }


def _apply_tds(t: TrainingDataset, body: TrainingDatasetIn, s: Session):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Dataset 이름을 입력하세요")
    dup = s.scalar(select(TrainingDataset).where(TrainingDataset.name == name))
    if dup and dup.id != t.id:
        raise HTTPException(400, f"이미 존재하는 Dataset 이름: {name}")
    if body.review_filter not in ("done", "any"):
        raise HTTPException(400, "review_filter must be done|any")
    for sp in body.job_splits.values():
        if sp and sp not in exporter.SPLITS:
            raise HTTPException(400, "job_splits 값은 train|val|test 여야 합니다")
    if any(v < 0 for v in body.ratios.values()):
        raise HTTPException(400, "스플릿 비율은 음수일 수 없습니다")
    jobs = []
    for jid in body.job_ids:
        j = s.get(LabelJob, jid)
        if j is None:
            raise HTTPException(400, f"Job #{jid}이 존재하지 않습니다")
        jobs.append(j)
    platforms = sorted({(j.project.robot_model or "").split("_")[0].lower()
                        for j in jobs if j.project.robot_model})
    if len(platforms) > 1:
        raise HTTPException(400, f"로봇 기종이 다른 프로젝트의 Job은 섞을 수 없습니다: {platforms}")
    t.name, t.description = name, body.description
    t.job_ids = body.job_ids
    t.review_filter = body.review_filter
    t.include_non_pass = body.include_non_pass
    t.ratios = {sp: float(body.ratios.get(sp, 0)) for sp in exporter.SPLITS}
    t.seed = body.seed
    t.job_splits = {k: v for k, v in body.job_splits.items() if v}


@app.get("/api/training-datasets")
def list_training_datasets(s: Session = Depends(db)):
    ts = s.scalars(select(TrainingDataset).order_by(TrainingDataset.id))
    return [tds_json(s, t) for t in ts]


@app.post("/api/training-datasets")
def create_training_dataset(body: TrainingDatasetIn, s: Session = Depends(db)):
    t = TrainingDataset()
    _apply_tds(t, body, s)
    s.add(t)
    s.commit()
    return tds_json(s, t)


@app.get("/api/training-datasets/{tid}")
def get_training_dataset(tid: int, s: Session = Depends(db)):
    t = s.get(TrainingDataset, tid) or _404("training dataset")
    return tds_json(s, t)


@app.patch("/api/training-datasets/{tid}")
def update_training_dataset(tid: int, body: TrainingDatasetIn,
                            s: Session = Depends(db)):
    t = s.get(TrainingDataset, tid) or _404("training dataset")
    _apply_tds(t, body, s)
    s.commit()
    return tds_json(s, t)


@app.delete("/api/training-datasets/{tid}")
def delete_training_dataset(tid: int, s: Session = Depends(db)):
    t = s.get(TrainingDataset, tid) or _404("training dataset")
    if any(x.status in ("pending", "running") for x in t.exports):
        raise HTTPException(409, "진행 중인 export가 있어 삭제할 수 없습니다")
    s.delete(t)
    s.commit()
    return {"ok": True}


@app.get("/api/training-datasets/{tid}/preview")
def preview_training_dataset(tid: int, s: Session = Depends(db)):
    t = s.get(TrainingDataset, tid) or _404("training dataset")
    try:
        res = exporter.resolve(s, t)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "warnings": res["warnings"],
        "splits": {sp: [{
            "episode_id": e.id, "episode_index": e.episode_index,
            "dataset_id": e.dataset_id,
            "project": e.dataset.project.name if e.dataset.project else "",
            "job": e.job.name if e.job else "",
            "length": e.length, "pass_status": e.pass_status,
            "review_status": e.review_status,
            "segments": len(e.segments), "task_text": e.task_text,
        } for e in res["splits"][sp]] for sp in exporter.SPLITS},
    }


@app.post("/api/training-datasets/{tid}/exports")
def start_export(tid: int, s: Session = Depends(db)):
    t = s.get(TrainingDataset, tid) or _404("training dataset")
    if any(x.status in ("pending", "running") for x in t.exports):
        raise HTTPException(409, "이미 진행 중인 export가 있습니다")
    try:
        res = exporter.resolve(s, t)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not any(res["splits"][sp] for sp in exporter.SPLITS):
        raise HTTPException(400, "포함되는 에피소드가 없습니다 (필터/Job 구성을 확인하세요)")
    x = ExportTask(training_dataset_id=t.id)
    s.add(x)
    s.commit()
    exporter.start_export(x.id)
    return {"id": x.id}


@app.get("/api/training-datasets/{tid}/exports")
def list_exports(tid: int, s: Session = Depends(db)):
    t = s.get(TrainingDataset, tid) or _404("training dataset")
    return [export_json(x) for x in reversed(t.exports)]


# ------------------------------------------------------------ static (UI)
UI_DIR = Path(os.environ.get(
    "ROBOLABEL_UI", Path(__file__).resolve().parents[3] / "frontend" / "dist"))
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
