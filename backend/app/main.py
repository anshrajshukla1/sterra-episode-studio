"""
app/main.py — FastAPI application entry point.

Lifespan:
  startup  → init DB tables, ensure data directories exist, start job runner
  shutdown → cancel job runner gracefully

Middleware:
  CORS — origins from settings.cors_origins (configurable via env)

Routers:
  /api/recordings — file discovery + metadata
  /api/jobs       — job creation, status, SSE stream
  /api/results    — QC results and health scores
  /api/files      — authenticated file serving (video, report)
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.pipeline import run_pipeline
from app.routers import files, jobs, recordings, results
from app.schemas import HealthResponse
from app.worker import job_runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Startup:
    1. Init DB (create tables if they don't exist — dev convenience)
    2. Ensure data directories exist on the filesystem
    3. Start the background job runner task

    Shutdown:
    4. Cancel the job runner task (allows CancelledError to propagate cleanly)
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Stera Episode Studio API starting up")

    await init_db()

    # ── Cleanup orphaned jobs from previous server session ────────────────────
    # Any job still 'running' or 'queued' after a restart is orphaned — the
    # asyncio worker died with the process. Reset them so the UI doesn't show
    # "Processing..." forever and the user can re-trigger the pipeline.
    try:
        from sqlalchemy import select as sa_select  # noqa: PLC0415
        from app.models import Job, Recording  # noqa: PLC0415
        async with AsyncSessionLocal() as db:
            # Reset orphaned jobs
            res = await db.execute(
                sa_select(Job).where(Job.status.in_(["running", "queued"]))
            )
            orphaned_jobs = res.scalars().all()
            for job in orphaned_jobs:
                job.status = "failed"
                job.error_msg = "Server restarted while job was running"
                logger.warning("Orphaned job %s reset to failed", job.id)

            # Reset recordings whose status is stuck on 'processing'
            res2 = await db.execute(
                sa_select(Recording).where(Recording.status == "processing")
            )
            stuck_recordings = res2.scalars().all()
            for rec in stuck_recordings:
                rec.status = "unprocessed"
                logger.warning("Stuck recording %s reset to unprocessed", rec.filename)

            if orphaned_jobs or stuck_recordings:
                await db.commit()
                logger.info(
                    "Startup cleanup: %d orphaned jobs, %d stuck recordings reset",
                    len(orphaned_jobs), len(stuck_recordings)
                )
    except Exception as cleanup_exc:
        logger.exception("Startup cleanup failed (non-fatal): %s", cleanup_exc)

    for path in (settings.recordings_dir, settings.episodes_dir):
        os.makedirs(path, exist_ok=True)
        logger.info("Data directory ready: %s", path)

    runner_task = asyncio.create_task(
        job_runner(AsyncSessionLocal, run_pipeline),
        name="job-runner",
    )
    logger.info("Background job runner started")

    yield  # ── Application runs here ─────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Stera Episode Studio API shutting down")
    runner_task.cancel()
    try:
        await runner_task
    except asyncio.CancelledError:
        logger.info("Job runner cancelled cleanly")


# ── Application factory ───────────────────────────────────────────────────────

app = FastAPI(
    title="Stera Episode Studio API",
    description=(
        "Backend for processing multimodal MCAP recordings into episode bundles. "
        "Supports Firebase auth, SSE job progress streaming, and QC reporting."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Disable OpenAPI docs in production by setting these to None
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(results.router, prefix="/api/results", tags=["results"])
app.include_router(files.router, prefix="/api/files", tags=["files"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="API health check",
    tags=["health"],
)
async def health() -> HealthResponse:
    """
    Returns 200 OK when the API is running.
    Does NOT check DB connectivity — use /api/recordings for a warm DB check.
    """
    return HealthResponse(
        status="ok",
        recordings_dir=settings.recordings_dir,
    )
