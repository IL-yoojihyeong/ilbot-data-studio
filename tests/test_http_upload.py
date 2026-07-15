"""HTTP 업로드 API 통합 테스트 — uvicorn 서브프로세스 + 합성 데이터 (CI 자급)."""
import io
import json
import os
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(tmp_path):
    port = _free_port()
    data = tmp_path / "data"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "robolabel.server.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        env={**os.environ, "ROBOLABEL_DATA": str(data)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/projects", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("server did not boot:\n"
                               + proc.stdout.read().decode(errors="replace")[-1500:])
        yield base, data
    finally:
        proc.terminate()
        proc.wait()


def req(base, method, path, body=None, raw=None, params="", ctype="application/json"):
    url = base + path + (f"?{params}" if params else "")
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"content-type": ctype})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def _tar_bytes(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                tar.add(p, arcname=str(p.relative_to(root)))
    return buf.getvalue()


def test_upload_roundtrip_and_errors(server, make_mini_dataset, tmp_path):
    base, data_dir = server
    pid = req(base, "POST", "/api/projects",
              {"name": "t", "usage": "Testing", "difficulty": "easy",
               "robot_model": "G2"})["id"]
    jid = req(base, "POST", f"/api/projects/{pid}/jobs", {"name": "j"})["id"]

    src = make_mini_dataset(tmp_path / "src_ds", [(10, "demo task")])
    payload = _tar_bytes(src)

    res = req(base, "POST", f"/api/jobs/{jid}/episodes", raw=payload,
              params="uuid=synthetic-upload-0001", ctype="application/x-tar")
    assert res["format"] == "lerobot_v3" and res["job_id"] == jid

    local = {str(p.relative_to(src)): p.stat().st_size
             for p in src.rglob("*") if p.is_file()}
    assert res["files"] == local                       # 크기 manifest 일치

    for _ in range(60):
        st = [t for t in req(base, "GET", f"/api/projects/{pid}/imports")
              if t["id"] == res["import_id"]][0]
        if st["status"] in ("done", "failed"):
            break
        time.sleep(0.3)
    assert st["status"] == "done", st
    eps = req(base, "GET", f"/api/projects/{pid}/episodes")
    assert len(eps) == 1 and eps[0]["length"] == 10 and eps[0]["job_id"] == jid

    # 중복 uuid → 409
    with pytest.raises(urllib.error.HTTPError) as e:
        req(base, "POST", f"/api/jobs/{jid}/episodes", raw=payload,
            params="uuid=synthetic-upload-0001", ctype="application/x-tar")
    assert e.value.code == 409

    # tar 아닌 본문 → 400 + 잔재 없음
    with pytest.raises(urllib.error.HTTPError) as e:
        req(base, "POST", f"/api/jobs/{jid}/episodes", raw=b"not a tar",
            params="uuid=bad-body-0001", ctype="application/x-tar")
    assert e.value.code == 400
    assert not (data_dir / "raw/bad-body-0001").exists()

    # 경로 탈출 tar → 400 차단
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo("../evil.txt")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(urllib.error.HTTPError) as e:
        req(base, "POST", f"/api/jobs/{jid}/episodes", raw=buf.getvalue(),
            params="uuid=evil-path-0001", ctype="application/x-tar")
    assert e.value.code == 400
    assert not (data_dir.parent / "evil.txt").exists()
    assert not (data_dir / "evil.txt").exists()
