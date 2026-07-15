"""SQLAlchemy models. SQLite for now; nothing here is SQLite-specific, so a
move to Postgres is a connection-string change."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer, String,
                        Table, Text, create_engine, event, inspect, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

DATA_DIR = Path(os.environ.get("ROBOLABEL_DATA", Path.home() / "robolabel_data"))


class Base(DeclarativeBase):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    """Profile, not an account: picked from a dropdown, no login (see SPEC)."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(20), default="labeler")  # admin|labeler|reviewer
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


project_members = Table(
    "project_members", Base.metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    usage: Mapped[str] = mapped_column(String(20), default="")       # Testing|Formal|R&D
    difficulty: Mapped[str] = mapped_column(String(20), default="")  # easy|middle|high
    action: Mapped[str] = mapped_column(Text, default="")            # 수행 Action 정의 (텍스트)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    start_date: Mapped[str] = mapped_column(String(10), default="")   # ISO date
    due_date: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|completed|archived
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # one robot type per project, picked at creation (ROBOT_TYPES in app.py);
    # imports are rejected when the data's platform doesn't match
    robot_model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])
    members: Mapped[list[User]] = relationship(secondary=project_members)
    jobs: Mapped[list["LabelJob"]] = relationship(back_populates="project",
                                                  cascade="all, delete-orphan")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="project",
                                                     cascade="all, delete-orphan")


class LabelJob(Base):
    """Unit of collection + labeling: one assignee, one canonical instruction."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    canonical_instruction: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="")  # easy|medium|hard
    object_name: Mapped[str] = mapped_column("object", String(200), default="")
    target_name: Mapped[str] = mapped_column("target", String(200), default="")
    environment: Mapped[str] = mapped_column(String(200), default="")
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    target_episodes: Mapped[int] = mapped_column(Integer, default=0)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    project: Mapped[Project] = relationship(back_populates="jobs")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    episodes: Mapped[list["Episode"]] = relationship(back_populates="job")


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    root: Mapped[str] = mapped_column(Text)               # lerobot dataset root dir
    source_format: Mapped[str] = mapped_column(String(50))  # agibot_g2 | lerobot_v3
    fps: Mapped[float] = mapped_column(default=30.0)
    robot_type: Mapped[str] = mapped_column(String(100), default="")
    info: Mapped[dict] = mapped_column(JSON, default=dict)  # meta/info.json cache
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    project: Mapped[Project] = relationship(back_populates="datasets")
    episodes: Mapped[list["Episode"]] = relationship(back_populates="dataset",
                                                     cascade="all, delete-orphan")


class Episode(Base):
    __tablename__ = "episodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    episode_index: Mapped[int] = mapped_column(Integer)
    length: Mapped[int] = mapped_column(Integer)
    # video_key -> {rel_path, from_ts, to_ts} (an episode may be a window of a
    # shared mp4 in v3 datasets)
    videos: Mapped[dict] = mapped_column(JSON, default=dict)
    data_file: Mapped[str] = mapped_column(Text, default="")  # rel path of parquet
    source_path: Mapped[str] = mapped_column(Text, default="")
    task_text: Mapped[str] = mapped_column(Text, default="")  # episode-level task
    pass_status: Mapped[str] = mapped_column(String(20), default="unlabeled")  # pass|non_pass|unlabeled
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    recorder_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[str] = mapped_column(String(10), default="")  # ISO date
    robot_serial: Mapped[str] = mapped_column(String(100), default="")
    # unlabeled -> labeled -> done (accept) | rejected (reject -> relabel -> labeled)
    review_status: Mapped[str] = mapped_column(String(20), default="unlabeled")
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    dataset: Mapped[Dataset] = relationship(back_populates="episodes")
    recorder: Mapped[User | None] = relationship(foreign_keys=[recorder_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_id])
    job: Mapped[LabelJob | None] = relationship(back_populates="episodes")
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="episode", cascade="all, delete-orphan",
        order_by="Segment.start_frame")


class Segment(Base):
    """Time-ranged VLA text label inside an episode."""
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"))
    start_frame: Mapped[int] = mapped_column(Integer)
    end_frame: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    skill: Mapped[str] = mapped_column(String(200), default="")
    episode: Mapped[Episode] = relationship(back_populates="segments")


class TrainingDataset(Base):
    """SPEC 'Dataset (스플릿 구성)': a cross-project bundle of Jobs plus split
    config, exported to a standalone LeRobot v3 dataset. Distinct from Dataset
    above, which is one imported/converted source dataset."""
    __tablename__ = "training_datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    job_ids: Mapped[list] = mapped_column(JSON, default=list)
    review_filter: Mapped[str] = mapped_column(String(20), default="done")  # done | any
    include_non_pass: Mapped[bool] = mapped_column(default=False)
    ratios: Mapped[dict] = mapped_column(JSON, default=dict)  # {train,val,test: weight}
    seed: Mapped[int] = mapped_column(Integer, default=42)
    # whole-job split overrides for unseen-task eval: {str(job_id): train|val|test}
    job_splits: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    exports: Mapped[list["ExportTask"]] = relationship(
        back_populates="training_dataset", cascade="all, delete-orphan",
        order_by="ExportTask.id")


class ExportTask(Base):
    __tablename__ = "export_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    training_dataset_id: Mapped[int] = mapped_column(ForeignKey("training_datasets.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|failed
    progress: Mapped[str] = mapped_column(Text, default="")
    out_path: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # resolved snapshot at export time
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    training_dataset: Mapped[TrainingDataset] = relationship(back_populates="exports")


class ImportTask(Base):
    __tablename__ = "import_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    path: Mapped[str] = mapped_column(Text)
    source_format: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|failed
    progress: Mapped[str] = mapped_column(Text, default="")
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


def _migrate(engine):
    """Add columns that exist on the models but not in the on-disk SQLite DB.

    SQLite fills pre-existing rows with the DEFAULT given in ADD COLUMN, which
    is all we need; dropped/renamed columns are left alone.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = (f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" '
                       f"{col.type.compile(engine.dialect)}")
                d = None
                if col.default is not None:
                    # callables are wrapped by SQLAlchemy; call with a null
                    # context to get the value (list -> [], dict -> {})
                    d = (col.default.arg(None) if col.default.is_callable
                         else col.default.arg)
                if isinstance(col.type, JSON):
                    if d is not None:
                        ddl += " DEFAULT '" + json.dumps(d) + "'"
                elif isinstance(d, str):
                    ddl += " DEFAULT '" + d.replace("'", "''") + "'"
                elif isinstance(d, bool):
                    ddl += f" DEFAULT {int(d)}"
                elif isinstance(d, (int, float)):
                    ddl += f" DEFAULT {d}"
                conn.execute(text(ddl))
        # Object Library removed (2026-07-07): drop leftover tables so a stale
        # FK (objects.creator_id -> users) can't block user deletion.
        for stale in ("project_objects", "objects"):
            if insp.has_table(stale):
                conn.execute(text(f"DROP TABLE {stale}"))


_engine = None
SessionLocal = None


def init_db(data_dir: Path | None = None):
    global _engine, SessionLocal
    d = Path(data_dir or DATA_DIR)
    d.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{d / 'robolabel.db'}",
                            connect_args={"check_same_thread": False})

    @event.listens_for(_engine, "connect")
    def _pragmas(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(_engine)
    _migrate(_engine)
    SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return SessionLocal


def get_session():
    if SessionLocal is None:
        init_db()
    return SessionLocal()
