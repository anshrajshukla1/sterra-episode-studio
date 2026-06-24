"""
app/schemas.py — Pydantic v2 schemas for all API request/response bodies.

Naming convention:
  <Model>Response  — what the API returns for a single object
  <Model>ListResponse — paginated / bulk list wrapper
  <Model>Create    — request body for creation endpoints
  SSEEvent         — individual server-sent event payload

All datetimes are serialized as ISO 8601 UTC strings by Pydantic.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared config
# ─────────────────────────────────────────────────────────────────────────────

class _ORMBase(BaseModel):
    """Base for all ORM-backed response schemas — enables from_attributes mode."""
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Recording schemas
# ─────────────────────────────────────────────────────────────────────────────

class RecordingResponse(_ORMBase):
    """Full recording detail returned by GET /api/recordings/{id}."""
    id: str
    filename: str
    filepath: str
    size_bytes: int
    duration_s: float | None = None
    stream_names: list[str] | None = None
    status: str
    error_msg: str | None = None
    created_at: datetime
    updated_at: datetime


class RecordingListItem(_ORMBase):
    """Lightweight recording summary used in list views."""
    id: str
    filename: str
    size_bytes: int
    duration_s: float | None = None
    stream_names: list[str] | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class RecordingListResponse(BaseModel):
    """Response envelope for GET /api/recordings."""
    items: list[RecordingListItem]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Job schemas
# ─────────────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    """Request body for POST /api/jobs."""
    recording_id: str = Field(
        ...,
        description="UUID of the recording to process",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    include_hand_tracking: bool = Field(
        default=False,
        description="Enable optional hand tracking (requires mediapipe HandTracker model)",
    )


class JobResponse(_ORMBase):
    """Job status returned by GET /api/jobs/{id} and POST /api/jobs."""
    id: str
    recording_id: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_msg: str | None = None


class JobListResponse(BaseModel):
    """Response envelope for GET /api/jobs (if implemented later)."""
    items: list[JobResponse]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Result schemas
# ─────────────────────────────────────────────────────────────────────────────

class ResultResponse(_ORMBase):
    """Full result detail returned by GET /api/results/{job_id}."""
    id: str
    job_id: str
    episode_path: str
    report_path: str | None = None
    health_score: float | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ResultListItem(_ORMBase):
    """Summary result used in the dashboard list."""
    id: str
    job_id: str
    health_score: float | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ResultListResponse(BaseModel):
    """Response envelope for GET /api/results/."""
    items: list[ResultListItem]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Error schema
# ─────────────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error body returned on 4xx/5xx responses."""
    detail: str
    code: str | None = None  # Optional machine-readable error code


# ─────────────────────────────────────────────────────────────────────────────
# SSE schemas
# ─────────────────────────────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    """
    Represents a single line emitted over the SSE stream.

    The SSE wire format is:  data: <line>\\n\\n
    This model is not directly serialized to JSON — it's used for
    internal typing only. The router formats the raw string into SSE format.
    """
    line: str
    is_done: bool = False       # True when STREAM_DONE sentinel received
    is_result: bool = False     # True when line starts with '__RESULT__:'
    health_score: float | None = None  # Parsed from __RESULT__ lines


# ─────────────────────────────────────────────────────────────────────────────
# Health check schema
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str
    recordings_dir: str
