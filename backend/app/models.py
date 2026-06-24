"""
app/models.py — SQLAlchemy ORM models for Stera Episode Studio.

Models:
  Recording — represents an .mcap file on disk
  Job       — a processing run triggered for a Recording
  Result    — the output of a successful Job (episode + QC report)

Design notes:
- IDs are UUID strings (String(36)) rather than native UUID columns for
  compatibility across Postgres/SQLite in tests without extra drivers.
- All timestamps use timezone-aware UTC datetimes.
- Cascade 'all, delete-orphan' on Recording.jobs means deleting a Recording
  also removes its associated Jobs (and transitively Results via Job.result).
- Enums are stored as VARCHAR strings rather than Postgres ENUM types to
  avoid migration headaches when values are added in the future.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


# ── Recording ─────────────────────────────────────────────────────────────────

class Recording(Base):
    """
    Represents a single .mcap recording file discovered on disk.

    Status lifecycle:
      unprocessed → processing → done
                             ↘ error
    """
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID primary key",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Original filename (e.g. session_001.mcap)",
    )
    filepath: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        unique=True,  # One DB row per unique file path — prevents duplicates on re-scan
        comment="Absolute path to the .mcap file on disk",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes at the time of discovery",
    )
    duration_s: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Recording duration in seconds (populated after processing)",
    )
    stream_names: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="List of stream names found in the recording (e.g. ['rgb', 'depth', 'pose'])",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unprocessed",
        comment="unprocessed | processing | done | error",
    )
    error_msg: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="Human-readable error detail when status='error'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
        lazy="selectin",  # Avoid N+1 on list endpoints
    )


# ── Job ───────────────────────────────────────────────────────────────────────

class Job(Base):
    """
    Represents a single processing run for a Recording.

    Status lifecycle:
      queued → running → done
                     ↘ failed
    """
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    recording_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("recordings.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="queued",
        comment="queued | running | done | failed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the job runner picks up this job",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the job finishes (done or failed)",
    )
    error_msg: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="Error detail when status='failed'",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    recording: Mapped["Recording"] = relationship(back_populates="jobs")
    result: Mapped["Result | None"] = relationship(
        back_populates="job",
        uselist=False,  # One-to-one
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ── Result ────────────────────────────────────────────────────────────────────

class Result(Base):
    """
    Stores the output of a successfully completed Job.

    Paths are absolute filesystem paths — the /api/files/ router
    uses these to serve files (after auth check).
    """
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id"),
        nullable=False,
        unique=True,  # One result per job
    )
    episode_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Absolute path to the exported episode directory",
    )
    report_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=True,
        comment="Absolute path to report.html (may be empty if QC step failed)",
    )
    health_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="0.0–1.0 QC health score from stera Evaluate (None if QC failed)",
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Duration, frame count, stream names, has_depth, has_pose",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    job: Mapped["Job"] = relationship(back_populates="result")
