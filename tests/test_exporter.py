"""Exporter 순수 로직 유닛 테스트 (로봇/실데이터 불필요 — CI용).

실행: uv run --extra server --with pytest pytest tests/
"""
from types import SimpleNamespace

import pytest

from robolabel.server import exporter
from robolabel.server.db import (Dataset, Episode, LabelJob, Project, Segment,
                                 TrainingDataset, init_db)


# ------------------------------------------------------------- frame_tasks
def _ep(task_text="", segments=()):
    return SimpleNamespace(
        task_text=task_text,
        segments=[SimpleNamespace(start_frame=a, end_frame=b, text=t)
                  for a, b, t in segments])


def test_frame_tasks_fallback_and_segments():
    e = _ep("pick the cup", [(0, 4, "reach"), (5, 8, "grasp")])
    tasks = exporter.frame_tasks(e, 12)
    assert tasks[0] == tasks[4] == "reach"          # inclusive 구간
    assert tasks[5] == tasks[8] == "grasp"
    assert tasks[9] == tasks[11] == "pick the cup"  # fallback


def test_frame_tasks_empty_segment_text_falls_back():
    e = _ep("base", [(0, 3, "  ")])
    assert exporter.frame_tasks(e, 5) == ["base"] * 5


def test_frame_tasks_clamps_out_of_range():
    e = _ep("", [(2, 999, "x")])
    tasks = exporter.frame_tasks(e, 5)
    assert tasks == ["", "", "x", "x", "x"]


# ---------------------------------------------------------------- resolve
@pytest.fixture()
def session(tmp_path):
    Session = init_db(tmp_path)
    s = Session()
    yield s
    s.close()


def _seed(s, n_eps=10, robot="G2"):
    p = Project(name="p1", robot_model=robot)
    s.add(p)
    s.flush()
    j = LabelJob(project_id=p.id, name="j1")
    s.add(j)
    d = Dataset(project_id=p.id, name="d1", root="/tmp/x", source_format="lerobot_v3")
    s.add(d)
    s.flush()
    for i in range(n_eps):
        s.add(Episode(dataset_id=d.id, job_id=j.id, episode_index=i, length=100,
                      review_status="done", pass_status="pass"))
    s.commit()
    return p, j


def test_resolve_ratio_split_deterministic(session):
    _, j = _seed(session, n_eps=10)
    t = TrainingDataset(name="t1", job_ids=[j.id], review_filter="done", include_non_pass=False,
                        ratios={"train": 80, "val": 10, "test": 10}, seed=7)
    r1 = exporter.resolve(session, t)
    r2 = exporter.resolve(session, t)
    counts = {sp: len(r1["splits"][sp]) for sp in exporter.SPLITS}
    assert counts == {"train": 8, "val": 1, "test": 1}
    assert [e.id for e in r1["splits"]["train"]] == [e.id for e in r2["splits"]["train"]]


def test_resolve_largest_remainder_sums_to_total(session):
    _, j = _seed(session, n_eps=7)
    t = TrainingDataset(name="t2", job_ids=[j.id], review_filter="done", include_non_pass=False,
                        ratios={"train": 60, "val": 25, "test": 15}, seed=1)
    r = exporter.resolve(session, t)
    assert sum(len(r["splits"][sp]) for sp in exporter.SPLITS) == 7


def test_resolve_filters_and_override(session):
    p, j = _seed(session, n_eps=4)
    eps = session.query(Episode).all()
    eps[0].review_status = "unlabeled"          # done 필터에 걸림
    eps[1].pass_status = "non_pass"             # 기본 제외
    j2 = LabelJob(project_id=p.id, name="j2")
    session.add(j2)
    session.flush()
    eps[2].job_id = j2.id                       # j2 전체는 test로 강제
    session.commit()

    # 주의: 세션에 add하지 않은 ORM 객체는 컬럼 default가 파이썬 속성에 반영되지
    # 않는다 — 실제 API 경로(_apply_tds)처럼 명시적으로 설정
    t = TrainingDataset(name="t3", job_ids=[j.id, j2.id],
                        review_filter="done", include_non_pass=False,
                        ratios={"train": 100, "val": 0, "test": 0}, seed=1,
                        job_splits={str(j2.id): "test"})
    r = exporter.resolve(session, t)
    assert len(r["splits"]["test"]) == 1 and r["splits"]["test"][0].id == eps[2].id
    assert len(r["splits"]["train"]) == 1       # 4개 중 필터 2개 + 강제 1개 제외
    assert any("리뷰 미완료" in w for w in r["warnings"])
    assert any("non_pass" in w for w in r["warnings"])


def test_resolve_rejects_mixed_robot(session):
    _, j = _seed(session, n_eps=1)
    p2 = Project(name="p2", robot_model="X2_Omnihand2025")
    session.add(p2)
    session.flush()
    j2 = LabelJob(project_id=p2.id, name="jx")
    session.add(j2)
    session.commit()
    t = TrainingDataset(name="t4", job_ids=[j.id, j2.id], review_filter="done", include_non_pass=False, ratios={"train": 100})
    with pytest.raises(ValueError):
        exporter.resolve(session, t)
