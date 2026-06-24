"""
app/routers/jobs.py — Job creation, status, and SSE log streaming.

POST /api/jobs
    Validate recording exists and isn't currently processing.
    Create Job row, enqueue to the background worker, return job_id.

GET /api/jobs/{job_id}
    Return current job status and timestamps.

GET /api/jobs/{job_id}/stream
    SSE endpoint. Streams log lines from the per-job asyncio.Queue.
    Sends a heartbeat comment every 15 seconds to keep connections alive
    through proxies and load balancers.
    Closes when STREAM_DONE sentinel is received from the queue.

Auth required on all endpoints.

SSE wire format (per EventSource spec):
    data: <log line>\\n\\n          — regular log line
    : heartbeat\\n\\n               — keepalive comment (ignored by browser)
    data: __STREAM_DONE__\\n\\n    — signals client to close connection
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_user_from_query
from app.config import settings
from app.database import get_db
from app.models import Job, Recording
from app.schemas import JobCreate, JobResponse
from app.worker import STREAM_DONE, enqueue_job, get_or_create_log_queue

logger = logging.getLogger(__name__)
router = APIRouter()

# Heartbeat interval in seconds — keeps SSE connections alive through proxies
_HEARTBEAT_INTERVAL = 15.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new processing job for a recording",
    responses={
        404: {"description": "Recording not found"},
        409: {"description": "Recording is already being processed"},
    },
)
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> JobResponse:
    """
    Create a Job for the given recording_id and enqueue it for processing.

    Rejects if:
    - recording_id doesn't exist in the DB (404)
    - Recording status is 'processing' or an active job is 'queued'/'running' (409)

    Returns the new Job with status='queued'.
    """
    # Validate recording exists
    stmt = select(Recording).where(Recording.id == body.recording_id)
    result = await db.execute(stmt)
    recording = result.scalar_one_or_none()

    if recording is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording '{body.recording_id}' not found",
        )

    # Guard against double-processing: check for any active (queued/running) job
    active_stmt = (
        select(Job)
        .where(Job.recording_id == body.recording_id)
        .where(Job.status.in_(["queued", "running"]))
    )
    active_result = await db.execute(active_stmt)
    active_job = active_result.scalar_one_or_none()

    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Recording '{body.recording_id}' already has an active job "
                f"(id={active_job.id}, status={active_job.status})"
            ),
        )

    # Create the Job row
    job = Job(recording_id=body.recording_id, status="queued")
    db.add(job)

    # Mark recording as processing so the list endpoint shows the right status
    recording.status = "processing"

    await db.commit()
    await db.refresh(job)

    # Enqueue to background worker
    await enqueue_job(
        job_id=job.id,
        recording_path=recording.filepath,
        episodes_dir=settings.episodes_dir,
        include_hand_tracking=body.include_hand_tracking,
    )

    logger.info(
        "Job %s created and enqueued for recording %s", job.id, body.recording_id
    )
    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status by ID",
    responses={404: {"description": "Job not found"}},
)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> JobResponse:
    """Return current status and timestamps for a job."""
    stmt = select(Job).where(Job.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}/stream",
    summary="Stream job log lines via Server-Sent Events",
    responses={
        404: {"description": "Job not found"},
        200: {"content": {"text/event-stream": {}}},
    },
)
async def stream_job_logs(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_user_from_query),
) -> StreamingResponse:
    """
    SSE endpoint — streams live log lines from the job's log queue.

    The client should connect with:
        EventSource('/api/jobs/<id>/stream', { withCredentials: true })
    and listen for 'message' events.

    Connection closes when:
    - The STREAM_DONE sentinel is dequeued (job finished or failed)
    - The client disconnects (request.is_disconnected())

    Heartbeat comments `: heartbeat` are sent every 15 seconds to prevent
    proxy timeouts. Most reverse proxies time out idle connections at 60s.
    """
    # Verify job exists before opening stream
    stmt = select(Job).where(Job.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    log_queue = get_or_create_log_queue(job_id)

    async def event_generator():
        """Async generator that yields SSE-formatted strings."""
        # If the job is already done/failed, drain any remaining queued lines first
        while True:
            # Check client disconnect to avoid holding the generator open forever
            if await request.is_disconnected():
                logger.info("SSE client disconnected for job %s", job_id)
                return

            try:
                # Wait for the next log line with a timeout equal to heartbeat interval
                line = await asyncio.wait_for(
                    log_queue.get(),
                    timeout=_HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                # No log line arrived in time — send heartbeat comment
                # EventSource spec: lines starting with ':' are comments
                yield ": heartbeat\n\n"
                continue

            if line == STREAM_DONE:
                # Signal the client to close and stop the generator
                yield f"data: {STREAM_DONE}\n\n"
                return

            # Regular log line — format as SSE data event
            # Escape newlines within the line to keep SSE format valid
            safe_line = line.replace("\n", " ").replace("\r", "")
            yield f"data: {safe_line}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            # Disable caching — SSE must always be live
            "Cache-Control": "no-cache",
            # Required for SSE to work through some proxies
            "X-Accel-Buffering": "no",
        },
    )
