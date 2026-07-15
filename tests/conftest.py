"""테스트 공용 헬퍼: 합성 미니 LeRobot 데이터셋 (외부 데이터 의존 없음)."""
import subprocess
from pathlib import Path

import numpy as np
import pytest

FPS = 10.0
JOINTS = [f"j{i}" for i in range(4)]
VKEY = "observation.images.head"


def mini_mp4(path: Path, n_frames: int, fps: float = FPS):
    """8x8 단색 mp4 (imageio-ffmpeg 정적 바이너리)."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ff, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=red:s=8x8:r={fps}:d={n_frames / fps}",
         "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture()
def make_mini_dataset(tmp_path):
    """make(root, episodes=[(n_frames, task), ...]) -> root 경로."""
    from robolabel.converter.writer import EpisodeData, LeRobotWriter

    def make(root: Path, episodes):
        w = LeRobotWriter(root=root, fps=FPS, robot_type="g2_synthetic",
                          joint_names=JOINTS,
                          video_info={VKEY: {"width": 8, "height": 8}})
        for i, (n, task) in enumerate(episodes):
            vid = tmp_path / f"src_ep{i}.mp4"
            mini_mp4(vid, n)
            w.add_episode(EpisodeData(
                state=np.random.rand(n, 4).astype(np.float32),
                action=np.random.rand(n, 4).astype(np.float32),
                task=task, videos={VKEY: vid},
                video_stats={VKEY: {"min": [[[0.0]]], "max": [[[1.0]]],
                                    "mean": [[[0.5]]], "std": [[[0.1]]],
                                    "count": [n]}},
                source_path=f"/synthetic/ep{i}"))
        w.finalize()
        return root

    return make
