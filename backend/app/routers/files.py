"""
app/routers/files.py — Authenticated file serving for episode output.

SECURITY: ALL endpoints in this router require authentication.
Episode directories contain processed video with faces — even though faces
are blurred, the recordings still constitute PII and must not be served
to unauthenticated clients. There are no public URLs for episode content.

GET /api/files/{job_id}/video
    Finds the .mp4 file in the episode_path directory and streams it.
    If multiple .mp4 files exist, serves the first one alphabetically.

GET /api/files/{job_id}/report
    Serves the QC HTML report (report.html) for the episode.

Both endpoints return 404 if:
- No result exists for the job_id
- The expected file is not found on disk (episode export may have failed)
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Result

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_result_or_404(job_id: str, db: AsyncSession) -> Result:
    """Fetch a Result row by job_id or raise HTTP 404."""
    stmt = select(Result).where(Result.job_id == job_id)
    res = await db.execute(stmt)
    result = res.scalar_one_or_none()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No result found for job '{job_id}'",
        )
    return result


def _find_mp4_in_dir(episode_path: str) -> str | None:
    """
    Find the first .mp4 file in the episode directory.

    Returns the absolute path, or None if no .mp4 file exists.
    Sorted alphabetically for determinism when multiple files exist.
    """
    if not os.path.isdir(episode_path):
        return None

    mp4_files = sorted(
        entry.path
        for entry in os.scandir(episode_path)
        if entry.is_file() and entry.name.lower().endswith(".mp4")
    )
    return mp4_files[0] if mp4_files else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/{job_id}/video",
    summary="Download the processed episode video (auth required)",
    responses={
        401: {"description": "Unauthorized — valid Firebase token required"},
        404: {"description": "Video file not found for this job"},
    },
)
async def serve_episode_video(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),  # Auth enforced here — never remove
) -> FileResponse:
    """
    Stream the exported episode video for the given job.

    Requires valid Firebase authentication.
    Returns the .mp4 file found in the episode_path directory.

    Security: Auth check is via `get_current_user` dependency above.
    The dependency raises HTTP 401 before this function body runs if the
    token is missing or invalid.
    """
    result = await _get_result_or_404(job_id, db)

    video_path = _find_mp4_in_dir(result.episode_path)
    if video_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No .mp4 video found in episode directory for job '{job_id}'. "
                f"Directory: {result.episode_path}"
            ),
        )

    if not os.path.isfile(video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video file no longer exists on disk: {video_path}",
        )

    filename = os.path.basename(video_path)
    logger.info("Serving video %s for job %s to user %s", filename, job_id, _user.get("sub"))

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=filename,
        # Inline disposition — lets the browser play the video directly
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/{job_id}/report",
    summary="Download the QC HTML report (auth required)",
    responses={
        401: {"description": "Unauthorized — valid Firebase token required"},
        404: {"description": "Report file not found for this job"},
    },
)
async def serve_qc_report(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),  # Auth enforced here — never remove
) -> FileResponse:
    """
    Serve the QC HTML report for the given job.

    Requires valid Firebase authentication.
    Returns the report.html file from the episode_path directory.

    Returns 404 if QC report generation failed during processing.
    """
    result = await _get_result_or_404(job_id, db)

    # report_path may be empty string if QC generation failed (non-fatal step)
    if not result.report_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No QC report was generated for job '{job_id}'. "
                "The QC step may have failed during processing — check job logs."
            ),
        )

    if not os.path.isfile(result.report_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"QC report file no longer exists on disk: {result.report_path}"
            ),
        )

    logger.info(
        "Serving QC report for job %s to user %s", job_id, _user.get("sub")
    )

    return FileResponse(
        path=result.report_path,
        media_type="text/html",
        filename="report.html",
        headers={"Content-Disposition": 'inline; filename="report.html"'},
    )
