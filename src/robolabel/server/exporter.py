"""TrainingDataset split resolution + LeRobot v3 export (SPEC 2단계).

Assembles a standalone LeRobot v3 dataset out of already-converted source
datasets: data parquets are re-indexed (episode_index / index) and task_index
is rewritten **per frame** from segment labels (fallback: episode task_text,
then ""). Videos are copied as-is when an episode owns its mp4, or cut with
ffmpeg when the source episode is a window of a shared file. Episodes are laid
out train → val → test so info.json `splits` are contiguous index ranges.

Platform metadata (canonical instruction 등) goes to meta/robolabel.json only —
never into meta/tasks.parquet (2026-07-05 결정).
"""

from __future__ import annotations

import datetime as dt
import json
import random
import re
import shutil
import subprocess
import threading
import traceback
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from ..converter.writer import CHUNKS_SIZE, _num_stats, aggregate_stats
from . import lerobot
from .db import (DATA_DIR, Episode, ExportTask, LabelJob, TrainingDataset,
                 get_session)

SPLITS = ("train", "val", "test")
DEFAULT_RATIOS = {"train": 80, "val": 10, "test": 10}


# ------------------------------------------------------------------ resolve
def resolve(s, tds: TrainingDataset) -> dict:
    """Resolve the dataset's job pool into per-split episode lists.

    Returns {"splits": {split: [Episode]}, "jobs": [LabelJob],
             "warnings": [str]}. Raises ValueError on robot-type mix.
    Deterministic: pool sorted by episode id, shuffled with the fixed seed.
    """
    warnings = []
    jobs = []
    for jid in tds.job_ids or []:
        j = s.get(LabelJob, jid)
        if j is None:
            warnings.append(f"Job #{jid}이 존재하지 않아 제외됩니다")
        else:
            jobs.append(j)

    platforms = sorted({(j.project.robot_model or "").split("_")[0].lower()
                        for j in jobs if j.project.robot_model})
    if len(platforms) > 1:
        raise ValueError(f"로봇 기종이 다른 프로젝트의 Job은 섞을 수 없습니다: {platforms}")

    eligible, n_review, n_pass = [], 0, 0
    for j in jobs:
        for e in j.episodes:
            if tds.review_filter == "done" and e.review_status != "done":
                n_review += 1
                continue
            if not tds.include_non_pass and e.pass_status == "non_pass":
                n_pass += 1
                continue
            eligible.append(e)
    if n_review:
        warnings.append(f"리뷰 미완료(done 아님) 에피소드 {n_review}개 제외")
    if n_pass:
        warnings.append(f"non_pass 에피소드 {n_pass}개 제외")

    split_eps = {sp: [] for sp in SPLITS}
    free = []
    for e in eligible:
        sp = (tds.job_splits or {}).get(str(e.job_id))
        if sp in SPLITS:
            split_eps[sp].append(e)
        else:
            free.append(e)

    free.sort(key=lambda e: e.id)
    random.Random(tds.seed).shuffle(free)
    ratios = {sp: max(0.0, float((tds.ratios or DEFAULT_RATIOS).get(sp, 0)))
              for sp in SPLITS}
    total_r = sum(ratios.values())
    if free and total_r <= 0:
        raise ValueError("스플릿 비율의 합이 0입니다")
    counts = {sp: 0 for sp in SPLITS}
    if free:
        exact = {sp: len(free) * ratios[sp] / total_r for sp in SPLITS}
        counts = {sp: int(exact[sp]) for sp in SPLITS}
        # largest remainder so counts sum exactly to the pool size
        leftovers = sorted(SPLITS, key=lambda sp: exact[sp] - counts[sp], reverse=True)
        for sp in leftovers[: len(free) - sum(counts.values())]:
            counts[sp] += 1
    pos = 0
    for sp in SPLITS:
        split_eps[sp].extend(free[pos:pos + counts[sp]])
        pos += counts[sp]

    return {"splits": split_eps, "jobs": jobs, "warnings": warnings}


# ------------------------------------------------------------- frame tasks
def frame_tasks(e: Episode, n_frames: int) -> list[str]:
    """Per-frame task text: segment text over its (inclusive) range, episode
    task_text where no segment covers, '' as last resort."""
    fallback = (e.task_text or "").strip()
    tasks = [fallback] * n_frames
    for sg in e.segments:  # ordered by start_frame; later start wins on overlap
        txt = (sg.text or "").strip()
        if not txt:
            continue
        for f in range(max(0, sg.start_frame), min(n_frames - 1, sg.end_frame) + 1):
            tasks[f] = txt
    return tasks


# ------------------------------------------------------------------ export
def start_export(export_id: int):
    t = threading.Thread(target=_run, args=(export_id,), daemon=True)
    t.start()
    return t


def _set(export_id: int, **fields):
    s = get_session()
    try:
        row = s.get(ExportTask, export_id)
        for k, v in fields.items():
            setattr(row, k, v)
        s.commit()
    finally:
        s.close()


def _slug(name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", name).strip("-")
    return slug or "dataset"


def _episode_stats_index(root: Path) -> dict[int, dict]:
    """episode_index -> stats dict, read from a source dataset's episodes meta."""
    out: dict[int, dict] = {}
    for f in lerobot.episodes_meta_files(root):
        t = pq.read_table(f)
        stat_keys = sorted({c.split("/")[1] for c in t.column_names
                            if c.startswith("stats/")})
        for row in t.to_pylist():
            stats = {}
            for k in stat_keys:
                try:
                    stats[k] = {f2: row[f"stats/{k}/{f2}"]
                                for f2 in ("min", "max", "mean", "std", "count")}
                except KeyError:
                    pass
            out[row["episode_index"]] = stats
    return out


def _cut_video(src: Path, dst: Path, from_ts: float, n_frames: int, fps: float):
    """Frame-accurate window cut (output-side seek → decodes from start)."""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), "-ss", f"{from_ts:.6f}", "-frames:v", str(n_frames),
           "-c:v", "libx264", "-preset", "fast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-g", str(int(round(fps))),
           "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg cut failed for {src.name}: {r.stderr[-300:]}")


def _run(export_id: int):
    s = get_session()
    try:
        task = s.get(ExportTask, export_id)
        tds = s.get(TrainingDataset, task.training_dataset_id)
        _set(export_id, status="running", progress="스플릿 해석 중")

        res = resolve(s, tds)
        ordered: list[tuple[Episode, str]] = []
        for sp in SPLITS:
            ordered.extend((e, sp) for e in res["splits"][sp])
        if not ordered:
            raise ValueError("포함되는 에피소드가 없습니다 (필터/Job 구성을 확인하세요)")

        # --- source dataset consistency (joint dims / cameras / fps)
        sources = {}
        for e, _ in ordered:
            sources.setdefault(e.dataset_id, e.dataset)
        infos = {did: d.info or lerobot.load_info(Path(d.root))
                 for did, d in sources.items()}
        ref_did = next(iter(infos))
        ref_info = infos[ref_did]

        def feat_sig(info):
            return {k: (f.get("dtype"), tuple(f.get("shape") or []))
                    for k, f in info.get("features", {}).items()}

        for did, info in infos.items():
            if feat_sig(info) != feat_sig(ref_info):
                raise ValueError(
                    f"소스 데이터셋 feature 불일치: '{sources[ref_did].name}' vs "
                    f"'{sources[did].name}' — 같은 관절/카메라 구성만 합칠 수 있습니다")
            if float(info.get("fps", 30)) != float(ref_info.get("fps", 30)):
                raise ValueError("소스 데이터셋 fps 불일치")

        fps = float(ref_info.get("fps", 30))
        video_keys = [k for k, f in ref_info["features"].items()
                      if f.get("dtype") == "video"]

        # an episode owns its mp4 iff no other episode of the same source
        # dataset references the same file (our converter writes one per
        # episode; generic v3 imports may share files with time windows)
        video_refs: dict[tuple[int, str], int] = {}
        for d in sources.values():
            for e in d.episodes:
                for v in e.videos.values():
                    key = (d.id, v["rel_path"])
                    video_refs[key] = video_refs.get(key, 0) + 1

        out_root = DATA_DIR / "exports" / f"{_slug(tds.name)}-e{export_id:03d}"
        if out_root.exists():
            raise FileExistsError(f"출력 경로가 이미 존재합니다: {out_root}")

        stats_by_source = {did: _episode_stats_index(Path(d.root))
                           for did, d in sources.items()}

        tasks_list: list[str] = []        # global meta/tasks.parquet order
        task_ids: dict[str, int] = {}

        def task_id(txt: str) -> int:
            if txt not in task_ids:
                task_ids[txt] = len(tasks_list)
                tasks_list.append(txt)
            return task_ids[txt]

        ep_rows = []                       # rows for new episodes meta
        stats_acc = []
        frame_offset = 0
        for new_idx, (e, sp) in enumerate(ordered):
            _set(export_id, progress=f"에피소드 {new_idx + 1}/{len(ordered)} 처리 중")
            src_root = Path(e.dataset.root)
            t = pq.read_table(src_root / e.data_file)
            if "episode_index" in t.column_names:
                import pyarrow.compute as pc
                t = t.filter(pc.equal(t["episode_index"], e.episode_index))
            T = t.num_rows
            if T != e.length:
                res["warnings"].append(
                    f"에피소드 #{e.id}: DB length({e.length}) ≠ parquet({T}) — parquet 기준 사용")

            ftasks = frame_tasks(e, T)
            tidx = np.array([task_id(x) for x in ftasks], dtype=np.int64)
            chunk, file = new_idx // CHUNKS_SIZE, new_idx % CHUNKS_SIZE

            def set_col(tbl, name, arr):
                if name in tbl.column_names:
                    tbl = tbl.drop_columns([name])
                return tbl.append_column(name, arr)

            t = set_col(t, "episode_index",
                        pa.array(np.full(T, new_idx, dtype=np.int64)))
            t = set_col(t, "index",
                        pa.array(np.arange(frame_offset, frame_offset + T, dtype=np.int64)))
            t = set_col(t, "task_index", pa.array(tidx))
            data_rel = f"data/chunk-{chunk:03d}/file-{file:03d}.parquet"
            (out_root / data_rel).parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(t, out_root / data_rel)

            # ---- videos
            video_meta = {}
            for vk in video_keys:
                v = e.videos.get(vk)
                if not v:
                    raise ValueError(f"에피소드 #{e.id}에 비디오 '{vk}'가 없습니다")
                src = src_root / v["rel_path"]
                dst = out_root / f"videos/{vk}/chunk-{chunk:03d}/file-{file:03d}.mp4"
                dst.parent.mkdir(parents=True, exist_ok=True)
                owns_file = video_refs.get((e.dataset_id, v["rel_path"]), 1) == 1
                if owns_file and float(v.get("from_ts") or 0) == 0.0:
                    shutil.copy2(src, dst)
                else:
                    _cut_video(src, dst, float(v.get("from_ts") or 0), T, fps)
                video_meta[vk] = {
                    "chunk_index": chunk, "file_index": file,
                    "from_timestamp": 0.0, "to_timestamp": round(T / fps, 6),
                }

            # ---- stats: carry over, recompute the re-indexed columns
            stats = dict(stats_by_source[e.dataset_id].get(e.episode_index) or {})
            if not stats:                     # foreign v3 without stats columns
                for col in ("observation.state", "action", "timestamp", "frame_index"):
                    if col in t.column_names:
                        stats[col] = _num_stats(
                            np.array(t[col].to_pylist(), dtype=np.float64))
            stats["episode_index"] = _num_stats(np.full((T, 1), new_idx))
            stats["index"] = _num_stats(
                np.arange(frame_offset, frame_offset + T).reshape(-1, 1))
            stats["task_index"] = _num_stats(tidx.reshape(-1, 1))
            stats_acc.append(stats)

            ep_task_texts = list(dict.fromkeys(ftasks))  # unique, frame order
            ep_rows.append({
                "episode_index": new_idx, "chunk": chunk, "file": file,
                "from_index": frame_offset, "to_index": frame_offset + T,
                "length": T, "tasks": ep_task_texts, "videos": video_meta,
                "stats": stats, "split": sp,
                "source_path": e.source_path,
                "quality": e.pass_status,
                "segments": [{"start_frame": sg.start_frame,
                              "end_frame": sg.end_frame, "action_text": sg.text,
                              "skill": sg.skill} for sg in e.segments],
            })
            frame_offset += T

        _set(export_id, progress="메타 파일 작성 중")
        _write_meta(out_root, ep_rows, tasks_list, stats_acc, ref_info, fps,
                    video_keys, res, tds, export_id)

        counts = {sp: len(res["splits"][sp]) for sp in SPLITS}
        _set(export_id, status="done", out_path=str(out_root),
             progress=f"완료: {len(ordered)}개 에피소드, {frame_offset}프레임",
             config=_config_snapshot(tds, res, counts, frame_offset))
    except Exception as e:
        traceback.print_exc()
        _set(export_id, status="failed", progress=f"{type(e).__name__}: {e}")
    finally:
        s.close()


def _config_snapshot(tds, res, counts, total_frames):
    return {
        "job_ids": tds.job_ids, "review_filter": tds.review_filter,
        "include_non_pass": tds.include_non_pass,
        "ratios": tds.ratios or DEFAULT_RATIOS, "seed": tds.seed,
        "job_splits": tds.job_splits or {},
        "counts": counts, "total_frames": total_frames,
        "warnings": res["warnings"],
    }


def _write_meta(out_root: Path, ep_rows, tasks_list, stats_acc, ref_info, fps,
                video_keys, res, tds, export_id):
    # ---- meta/episodes (same column layout as converter/writer.py)
    cols: dict[str, list] = {
        "episode_index": [], "data/chunk_index": [], "data/file_index": [],
        "dataset_from_index": [], "dataset_to_index": [],
    }
    for vk in video_keys:
        for f in ("chunk_index", "file_index", "from_timestamp", "to_timestamp"):
            cols[f"videos/{vk}/{f}"] = []
    cols.update({"tasks": [], "length": [], "source_path": [],
                 "split": [], "quality": []})
    stat_keys = sorted(set().union(*(r["stats"].keys() for r in ep_rows)))
    for sk in stat_keys:
        for f in ("min", "max", "mean", "std", "count"):
            cols[f"stats/{sk}/{f}"] = []
    cols["meta/episodes/chunk_index"] = []
    cols["meta/episodes/file_index"] = []

    for r in ep_rows:
        cols["episode_index"].append(r["episode_index"])
        cols["data/chunk_index"].append(r["chunk"])
        cols["data/file_index"].append(r["file"])
        cols["dataset_from_index"].append(r["from_index"])
        cols["dataset_to_index"].append(r["to_index"])
        for vk in video_keys:
            vm = r["videos"][vk]
            for f in ("chunk_index", "file_index", "from_timestamp", "to_timestamp"):
                cols[f"videos/{vk}/{f}"].append(vm[f])
        cols["tasks"].append(r["tasks"])
        cols["length"].append(r["length"])
        cols["source_path"].append(r["source_path"])
        cols["split"].append(r["split"])
        cols["quality"].append(r["quality"])
        for sk in stat_keys:
            st = r["stats"].get(sk)
            for f in ("min", "max", "mean", "std", "count"):
                cols[f"stats/{sk}/{f}"].append(st[f] if st else None)
        cols["meta/episodes/chunk_index"].append(0)
        cols["meta/episodes/file_index"].append(0)

    path = out_root / "meta/episodes/chunk-000/file-000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(cols), path)

    # ---- meta/tasks.parquet (training tasks only — no canonical instructions)
    pq.write_table(pa.table({
        "task_index": pa.array(range(len(tasks_list)), type=pa.int64()),
        "task": pa.array(tasks_list, type=pa.string()),
    }), out_root / "meta/tasks.parquet")

    # ---- meta/stats.json
    # aggregate only keys present in every episode (foreign sources may lack some)
    shared_keys = set(stats_acc[0]).intersection(*stats_acc[1:]) if stats_acc else set()
    agg_input = [{k: st[k] for k in shared_keys} for st in stats_acc]
    if shared_keys:
        (out_root / "meta/stats.json").write_text(
            json.dumps(aggregate_stats(agg_input), indent=4))

    # ---- meta/info.json — splits as contiguous ranges (train → val → test)
    splits, pos = {}, 0
    for sp in SPLITS:
        n = len(res["splits"][sp])
        if n:
            splits[sp] = f"{pos}:{pos + n}"
            pos += n
    info = {
        "codebase_version": ref_info.get("codebase_version", "v3.0"),
        "robot_type": ref_info.get("robot_type", ""),
        "total_episodes": len(ep_rows),
        "total_frames": ep_rows[-1]["to_index"] if ep_rows else 0,
        "total_tasks": len(tasks_list),
        "chunks_size": CHUNKS_SIZE,
        "fps": fps,
        "splits": splits,
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
        "features": ref_info["features"],
        "data_files_size_in_mb": ref_info.get("data_files_size_in_mb", 100),
        "video_files_size_in_mb": ref_info.get("video_files_size_in_mb", 200),
    }
    (out_root / "meta/info.json").write_text(json.dumps(info, indent=4))

    # ---- meta/robolabel.json — platform metadata kept out of tasks.parquet
    projects = {}
    for j in res["jobs"]:
        p = j.project
        projects[p.id] = {
            "id": p.id, "name": p.name, "usage": p.usage,
            "difficulty": p.difficulty, "action": p.action,
            "robot_model": p.robot_model,
        }
    robolabel = {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "export_id": export_id,
        "training_dataset": {"id": tds.id, "name": tds.name,
                             "description": tds.description},
        "config": {
            "review_filter": tds.review_filter,
            "include_non_pass": tds.include_non_pass,
            "ratios": tds.ratios or DEFAULT_RATIOS, "seed": tds.seed,
            "job_splits": tds.job_splits or {},
        },
        "projects": list(projects.values()),
        "jobs": [{
            "id": j.id, "project_id": j.project_id, "name": j.name,
            "canonical_instruction": j.canonical_instruction,
            "object": j.object_name, "success_criteria": j.success_criteria,
        } for j in res["jobs"]],
        "splits": info["splits"],
        "episodes": [{
            "episode_index": r["episode_index"], "split": r["split"],
            "length": r["length"], "quality": r["quality"],
            "tasks": r["tasks"], "segments": r["segments"],
            "source_path": r["source_path"],
        } for r in ep_rows],
        "warnings": res["warnings"],
    }
    (out_root / "meta/robolabel.json").write_text(
        json.dumps(robolabel, ensure_ascii=False, indent=2))
