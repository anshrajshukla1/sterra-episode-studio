"""
app/routers/recordings.py — Recordings discovery and metadata endpoints.

GET /api/recordings
    Scans RECORDINGS_DIR for .mcap files, validates magic bytes, upserts
    records into the DB (new files → insert, existing → update size only),
    and returns the full list sorted by created_at desc.

GET /api/recordings/{id}
    Returns a single recording by DB id.

Design:
- The scan-on-list approach means we don't need a file-watcher daemon.
  Every list request is a fresh scan — suitable for a single-user internal
  tool where the directory is managed externally (e.g. mounted volume).
- Files that fail MCAP magic byte validation are skipped (logged at WARNING).
- Files already in the DB (matched by filepath) are not re-inserted — only
  their size_bytes is updated in case the file was replaced.
- Auth required on both endpoints — recordings contain paths to PII data.
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Recording
from app.pipeline import validate_mcap_file
from app.schemas import RecordingListResponse, RecordingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _scan_and_upsert(db: AsyncSession, recordings_dir: str) -> list[Recording]:
    """
    Walk recordings_dir, validate MCAP magic bytes, and upsert to DB.

    Returns the list of all Recording rows after the upsert, ordered by
    created_at descending (newest first).
    """
    from app.config import settings  # avoid circular at module level

    # Collect .mcap files from the directory (non-recursive — single flat dir)
    mcap_files: list[tuple[str, str, int]] = []  # (filepath, filename, size_bytes)
    if not os.path.isdir(recordings_dir):
        logger.warning("RECORDINGS_DIR does not exist: %s", recordings_dir)
        return []

    for entry in os.scandir(recordings_dir):
        if not entry.is_file():
            continue
        if not entry.name.lower().endswith(".mcap"):
            continue
        try:
            size_bytes = entry.stat().st_size
        except OSError as exc:
            logger.warning("Cannot stat file %s: %s", entry.path, exc)
            continue

        # Validate MCAP magic bytes before touching the DB
        is_valid, err = validate_mcap_file(entry.path)
        if not is_valid:
            logger.warning("Skipping invalid MCAP file %s: %s", entry.path, err)
            continue

        mcap_files.append((entry.path, entry.name, size_bytes))

    # Upsert: load existing rows keyed by filepath
    existing_stmt = select(Recording)
    existing_result = await db.execute(existing_stmt)
    existing_by_path: dict[str, Recording] = {
        r.filepath: r for r in existing_result.scalars().all()
    }

    for filepath, filename, size_bytes in mcap_files:
        if filepath in existing_by_path:
            # File already known — update size in case it was replaced on disk
            rec = existing_by_path[filepath]
            if rec.size_bytes != size_bytes:
                rec.size_bytes = size_bytes
                rec.updated_at = datetime.now(timezone.utc)
                logger.debug("Updated size for recording %s", rec.id)
        else:
            # New file — insert
            new_rec = Recording(
                filename=filename,
                filepath=filepath,
                size_bytes=size_bytes,
                status="unprocessed",
            )
            db.add(new_rec)
            logger.info("Discovered new recording: %s", filename)

    await db.commit()

    # Return full list sorted newest first
    result = await db.execute(
        select(Recording).order_by(Recording.created_at.desc())
    )
    return list(result.scalars().all())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=RecordingListResponse,
    summary="List all recordings (scans disk on each call)",
)
async def list_recordings(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> RecordingListResponse:
    """
    Scan RECORDINGS_DIR for .mcap files, upsert to DB, return full list.

    Invalid MCAP files (bad magic bytes) are silently skipped.
    Auth required — recording paths must not leak to unauthenticated clients.
    """
    from app.config import settings

    recordings = await _scan_and_upsert(db, settings.recordings_dir)
    return RecordingListResponse(
        items=recordings,  # type: ignore[arg-type]
        total=len(recordings),
    )


@router.get(
    "/{recording_id}",
    response_model=RecordingResponse,
    summary="Get a single recording by ID",
    responses={404: {"description": "Recording not found"}},
)
async def get_recording(
    recording_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> RecordingResponse:
    """
    Return full detail for a single recording.

    Raises 404 if the recording ID does not exist in the DB.
    Auth required.
    """
    stmt = select(Recording).where(Recording.id == recording_id)
    result = await db.execute(stmt)
    recording = result.scalar_one_or_none()

    if recording is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording '{recording_id}' not found",
        )

    return RecordingResponse.model_validate(recording)
