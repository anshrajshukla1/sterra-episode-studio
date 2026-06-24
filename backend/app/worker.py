"""
app/worker.py — In-process async job runner.

Design:
- Uses a single asyncio.Queue consumed by one background task (job_runner).
- Each job gets its own asyncio.Queue for log lines, consumed by SSE endpoints.
- No external broker (no Celery, no Redis, no RQ) — this is a single-user
  internal tool and the added infra complexity is unjustified. See DECISIONS.md.

Job lifecycle:
  POST /api/jobs → enqueue_job() → _job_queue → job_runner() picks it up
                                   ↓
                              per-job log_queue → SSE /api/jobs/{id}/stream
                                   ↓
                           DB update (status, result)

Thread safety:
- _job_queue and _job_log_queues are only ever touched from the asyncio event
  loop thread — no locks needed.
- emit() is a sync function that uses put_nowait() — safe to call from inside
  run_in_executor() workers because Queue.put_nowait() is thread-safe.

Log queue cleanup:
- Log queues are never explicitly removed from _job_log_queues because the
  memory cost is negligible for a single-user tool (< 100 bytes per job).
  A production multi-tenant system would need a TTL-based cleanup strategy.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────────────────────────

# The single job queue: tuples of (job_id, recording_path, episodes_dir, include_hand_tracking)
_job_queue: asyncio.Queue[tuple[str, str, str, bool]] = asyncio.Queue()

# Per-job log queues: job_id → asyncio.Queue[str]
# SSE endpoints await on these queues to stream log lines to the browser.
_job_log_queues: dict[str, asyncio.Queue[str]] = {}

# Sentinel value placed at the end of a log queue to signal stream completion.
# The SSE endpoint closes the connection when it dequeues this value.
STREAM_DONE = "__STREAM_DONE__"

# Prefix for the health score result line emitted at the end of a successful job.
# Format: "__RESULT__:<health_score_or_None>"
RESULT_PREFIX = "__RESULT__:"


# ── Queue helpers ─────────────────────────────────────────────────────────────

def get_or_create_log_queue(job_id: str) -> asyncio.Queue[str]:
    """
    Return the log queue for job_id, creating it if it doesn't exist.

    maxsize=1000 prevents unbounded memory growth if the SSE consumer
    disconnects while the job is still running.
    """
    if job_id not in _job_log_queues:
        _job_log_queues[job_id] = asyncio.Queue(maxsize=1000)
    return _job_log_queues[job_id]


async def enqueue_job(
    job_id: str,
    recording_path: str,
    episodes_dir: str,
    include_hand_tracking: bool = False,
) -> asyncio.Queue[str]:
    """
    Enqueue a job for processing and return its log queue.

    The caller (POST /api/jobs) uses the returned queue reference so it can
    redirect the SSE endpoint to the right queue without a second lookup.
    """
    log_q = get_or_create_log_queue(job_id)
    await _job_queue.put((job_id, recording_path, episodes_dir, include_hand_tracking))
    logger.info("Job %s enqueued (queue depth: %d)", job_id, _job_queue.qsize())
    return log_q


# ── Job runner ────────────────────────────────────────────────────────────────

async def job_runner(
    db_session_factory: async_sessionmaker,
    pipeline_fn,
) -> None:
    """
    Background task: consume jobs from _job_queue and run the pipeline.

    Runs forever — cancelled only on app shutdown (lifespan context manager).

    Args:
        db_session_factory: AsyncSessionLocal — used to open DB sessions.
        pipeline_fn:        The run_pipeline coroutine function from pipeline.py.
                            Injected to allow easy mocking in tests.
    """
    logger.info("Job runner started and listening for work")

    while True:
        job_id, recording_path, episodes_dir, include_hand_tracking = (
            await _job_queue.get()
        )
        log_q = get_or_create_log_queue(job_id)

        def emit(msg: str) -> None:
            """
            Thread-safe sync callback — writes a log line to the SSE queue.

            Uses put_nowait() so it's safe to call from executor threads.
            Drops the line silently if the queue is full (consumer is slow).
            Dropping non-critical log lines is preferable to blocking the
            pipeline thread or raising an error mid-processing.
            """
            try:
                log_q.put_nowait(msg)
            except asyncio.QueueFull:
                # Consumer is slow or disconnected — drop the line
                logger.debug("SSE queue full for job %s — dropping log line", job_id)

        try:
            # ── Mark job as running ──────────────────────────────────────────
            async with db_session_factory() as db:
                from app.models import Job  # noqa: PLC0415
                from sqlalchemy import select  # noqa: PLC0415

                stmt = select(Job).where(Job.id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one_or_none()

                if job is None:
                    logger.error(
                        "Job %s not found in DB — skipping (was it deleted?)", job_id
                    )
                    emit(f"[error] Job {job_id} not found in database")
                    emit(STREAM_DONE)
                    _job_queue.task_done()
                    continue

                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info("Job %s status → running", job_id)

            # ── Run the pipeline ─────────────────────────────────────────────
            pipeline_result = await pipeline_fn(
                recording_path=recording_path,
                job_id=job_id,
                episodes_dir=episodes_dir,
                emit=emit,
                include_hand_tracking=include_hand_tracking,
            )

            # ── Persist result and update statuses ───────────────────────────
            async with db_session_factory() as db:
                from app.models import Job, Recording, Result  # noqa: PLC0415
                from sqlalchemy import select  # noqa: PLC0415

                # Update job status
                stmt = select(Job).where(Job.id == job_id)
                res = await db.execute(stmt)
                job = res.scalar_one_or_none()

                if job is not None:
                    job.status = "done"
                    job.completed_at = datetime.now(timezone.utc)

                # Persist Result
                db_result = Result(
                    job_id=job_id,
                    episode_path=pipeline_result.episode_path,
                    report_path=pipeline_result.report_path or None,
                    health_score=pipeline_result.health_score,
                    metadata_json=pipeline_result.metadata,
                )
                db.add(db_result)

                # Update Recording status and metadata
                if job is not None:
                    stmt2 = select(Recording).where(Recording.id == job.recording_id)
                    res2 = await db.execute(stmt2)
                    recording = res2.scalar_one_or_none()
                    if recording is not None:
                        recording.status = "done"
                        recording.duration_s = pipeline_result.metadata.get("duration_s")
                        recording.stream_names = pipeline_result.metadata.get(
                            "stream_names", []
                        )

                await db.commit()
                logger.info("Job %s status → done", job_id)

            # Emit the result line so the SSE client can pick up the health score
            emit(f"{RESULT_PREFIX}{pipeline_result.health_score}")

        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed with unexpected error", job_id)
            emit(f"[error] Pipeline failed: {exc}")

            # ── Mark job and recording as failed ─────────────────────────────
            try:
                async with db_session_factory() as db:
                    from app.models import Job, Recording  # noqa: PLC0415
                    from sqlalchemy import select  # noqa: PLC0415

                    stmt = select(Job).where(Job.id == job_id)
                    res = await db.execute(stmt)
                    job = res.scalar_one_or_none()

                    if job is not None:
                        job.status = "failed"
                        job.completed_at = datetime.now(timezone.utc)
                        job.error_msg = str(exc)[:2048]  # Truncate to column size

                        stmt2 = select(Recording).where(Recording.id == job.recording_id)
                        res2 = await db.execute(stmt2)
                        recording = res2.scalar_one_or_none()
                        if recording is not None:
                            recording.status = "error"
                            recording.error_msg = str(exc)[:2048]

                    await db.commit()
                    logger.info("Job %s status → failed", job_id)

            except Exception as db_exc:
                # DB update failure after job failure — log and continue.
                # The SSE consumer will still see the error log lines.
                logger.exception(
                    "Failed to update DB after job %s failure: %s", job_id, db_exc
                )

        finally:
            # Always emit the stream-done sentinel so SSE clients close cleanly
            emit(STREAM_DONE)
            _job_queue.task_done()
