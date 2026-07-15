"""LeRobotWriter.resume(append) 라운드트립 테스트 — 합성 미니 에피소드 (CI용)."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from robolabel.converter.writer import EpisodeData, LeRobotWriter
from robolabel.server import lerobot

JOINTS = [f"j{i}" for i in range(4)]
FPS = 10.0


def _mini_mp4(path: Path, n_frames: int):
    """8x8 단색 mp4 (imageio-ffmpeg 정적 바이너리 사용)."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ff, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=red:s=8x8:r={FPS}:d={n_frames / FPS}",
         "-pix_fmt", "yuv420p", str(path)], check=True)


def _add(writer: LeRobotWriter, tmp: Path, n: int, task: str, tag: str):
    vid = tmp / f"{tag}.mp4"
    _mini_mp4(vid, n)
    writer.add_episode(EpisodeData(
        state=np.random.rand(n, 4).astype(np.float32),
        action=np.random.rand(n, 4).astype(np.float32),
        task=task, videos={"observation.images.head": vid},
        video_stats={"observation.images.head": {
            "min": [[[0.0]]] * 1, "max": [[[1.0]]],
            "mean": [[[0.5]]], "std": [[[0.1]]], "count": [n],
        }},
        source_path=f"/src/{tag}"))
    writer.finalize()


def test_resume_appends_episodes(tmp_path):
    root = tmp_path / "ds"
    w = LeRobotWriter(root=root, fps=FPS, robot_type="testbot",
                      joint_names=JOINTS,
                      video_info={"observation.images.head": {"width": 8, "height": 8}})
    _add(w, tmp_path, 20, "task A", "ep0")

    # 새 프로세스처럼 resume해서 2개 추가 (다른/같은 task 혼합)
    w2 = LeRobotWriter.resume(root)
    assert w2._frame_offset == 20 and len(w2.episodes) == 1
    assert w2.joint_names == JOINTS and w2.fps == FPS
    _add(w2, tmp_path, 10, "task B", "ep1")
    w3 = LeRobotWriter.resume(root)
    _add(w3, tmp_path, 15, "task A", "ep2")

    info = json.loads((root / "meta/info.json").read_text())
    assert info["total_episodes"] == 3
    assert info["total_frames"] == 45
    assert info["total_tasks"] == 2                    # A, B (중복 없이)

    eps = lerobot.scan_episodes(root)
    assert [e["length"] for e in eps] == [20, 10, 15]
    assert [e["task"] for e in eps] == ["task A", "task B", "task A"]
    assert [e["episode_index"] for e in eps] == [0, 1, 2]
    for i in range(3):
        assert (root / f"data/chunk-000/file-{i:03d}.parquet").exists()
        assert (root / f"videos/observation.images.head/chunk-000/file-{i:03d}.mp4").exists()

    # 전역 index 연속성 + stats 집계 카운트
    ts = lerobot.read_timeseries(root, eps[2]["data_file"], 2)
    assert ts["length"] == 15
    stats = json.loads((root / "meta/stats.json").read_text())
    assert stats["observation.state"]["count"] == [45]


def test_resume_empty_dataset_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        LeRobotWriter.resume(tmp_path / "nothing")
