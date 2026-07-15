"""Folder-registration import: detect format, convert if needed, register episodes.

Runs in a background thread; progress is written to the ImportTask row.
"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

from . import lerobot
from .db import DATA_DIR, Dataset, Episode, ImportTask, Project, get_session


def detect_format(path: Path) -> str:
    path = Path(path)
    if (path / "meta" / "info.json").exists():
        return "lerobot_v3"
    if (path / "meta_info.json").exists():
        return "agibot_g2_episode"
    if any(p.is_dir() and (p / "meta_info.json").exists() for p in path.iterdir()):
        return "agibot_g2_batch"
    raise ValueError(f"unrecognized data format at {path}")


def start_import(task_id: int):
    t = threading.Thread(target=_run, args=(task_id,), daemon=True)
    t.start()
    return t


def _set(task_id: int, **fields):
    s = get_session()
    try:
        row = s.get(ImportTask, task_id)
        for k, v in fields.items():
            setattr(row, k, v)
        s.commit()
    finally:
        s.close()


def _run(task_id: int):
    s = get_session()
    task = s.get(ImportTask, task_id)
    s.close()
    try:
        _set(task_id, status="running", progress="detecting format")
        src = Path(task.path)
        fmt = detect_format(src)

        if fmt == "lerobot_v3":
            root, source_format = src, "lerobot_v3"
        else:
            episode_dirs = [src] if fmt == "agibot_g2_episode" else sorted(
                p for p in src.iterdir() if (p / "meta_info.json").exists())
            root = DATA_DIR / "datasets" / src.name
            source_format = "agibot_g2"
            from ..converter.cli import DEFAULT_CAMERAS, convert
            _set(task_id, progress=f"converting {len(episode_dirs)} episode(s)")
            convert(episode_dirs, root, DEFAULT_CAMERAS,
                    log=lambda m: _set(task_id, progress=m))

        _set(task_id, progress="registering episodes")
        info = lerobot.load_info(root)
        eps = lerobot.scan_episodes(root)

        s = get_session()
        try:
            # one robot type per project (picked at creation). Data metadata
            # carries strings like "agibot_g2"; the project type is e.g.
            # "G2_Omnihand2025" — compare on the platform prefix (g2/x2).
            robot = str(info.get("robot_type", ""))
            proj = s.get(Project, task.project_id)
            if proj.robot_model and robot:
                platform = proj.robot_model.split("_")[0].lower()
                if platform not in robot.lower():
                    raise ValueError(
                        f"로봇 기종 불일치: 프로젝트는 '{proj.robot_model}', "
                        f"데이터는 '{robot}'")
            if not proj.robot_model and robot:
                proj.robot_model = robot
            ds = Dataset(
                project_id=task.project_id, name=src.name, root=str(root),
                source_format=source_format, fps=float(info.get("fps", 30)),
                robot_type=robot, info=info)
            s.add(ds)
            s.flush()
            for e in eps:
                s.add(Episode(
                    dataset_id=ds.id, job_id=task.job_id,
                    episode_index=e["episode_index"], length=e["length"],
                    videos=e["videos"], data_file=e["data_file"],
                    source_path=e["source_path"] or str(src),
                    task_text=e["task"]))
            s.commit()
            _set(task_id, status="done", dataset_id=ds.id,
                 progress=f"{len(eps)} episodes registered")
        finally:
            s.close()
    except Exception as e:
        traceback.print_exc()
        _set(task_id, status="failed", progress=f"{type(e).__name__}: {e}")
