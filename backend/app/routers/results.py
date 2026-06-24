"""
app/routers/results.py — QC result retrieval endpoints.

GET /api/results/
    Returns all results with health scores, sorted by created_at desc.
    Used by the dashboard to show a leaderboard / health score overview.

GET /api/results/{job_id}
    Returns the full result for a specific job, including episode_path,
    report_path, health_score, and metadata_json.

Auth required on both endpoints.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Result
from app.schemas import ResultListResponse, ResultResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=ResultListResponse,
    summary="List all results with health scores",
)
async def list_results(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> ResultListResponse:
    """
    Return all processing results ordered by created_at descending.

    This endpoint is intended for the dashboard health-score leaderboard.
    Full metadata is included so the frontend can display stream info.
    Auth required.
    """
    stmt = select(Result).order_by(Result.created_at.desc())
    result = await db.execute(stmt)
    results = list(result.scalars().all())
    return ResultListResponse(
        items=results,  # type: ignore[arg-type]
        total=len(results),
    )


@router.get(
    "/{job_id}",
    response_model=ResultResponse,
    summary="Get result for a specific job",
    responses={404: {"description": "Result not found for this job ID"}},
)
async def get_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> ResultResponse:
    """
    Return the full result for the given job_id.

    Returns 404 if the job hasn't finished yet or doesn't exist.
    The caller should poll GET /api/jobs/{job_id} first to confirm
    status='done' before fetching the result.
    Auth required.
    """
    stmt = select(Result).where(Result.job_id == job_id)
    result = await db.execute(stmt)
    db_result = result.scalar_one_or_none()

    if db_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No result found for job '{job_id}'. "
                "The job may still be running or may have failed."
            ),
        )

    return ResultResponse.model_validate(db_result)
