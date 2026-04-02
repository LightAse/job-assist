from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.schemas.jobs import (
    JobDetail,
    RunCompatibilityCheckRequest,
    RunCompatibilityCheckResponse,
    StoredJob,
)
from app.services.compatibility import get_compatibility_service
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderRequestError,
    CompatibilityProviderResponseError,
    CompatibilityProviderTimeoutError,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[StoredJob])
def list_jobs(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[StoredJob]:
    return job_store.list_jobs()


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> JobDetail:
    job = job_store.get_job_detail(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )
    return job


@router.post("/{job_id}/compatibility-checks", response_model=RunCompatibilityCheckResponse)
def run_compatibility_check(
    job_id: int,
    payload: RunCompatibilityCheckRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> RunCompatibilityCheckResponse:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    snapshot = job_store.get_latest_snapshot_for_job(job_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No job snapshot is available for compatibility checking.",
        )

    resume_profile = job_store.get_resume_profile(payload.resume_profile_id)
    if resume_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume profile not found.",
        )

    try:
        evaluation = get_compatibility_service().evaluate(
            resume_profile=resume_profile,
            snapshot=snapshot,
        )
    except CompatibilityProviderConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error
    except CompatibilityProviderTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Compatibility provider timed out.",
        ) from error
    except CompatibilityProviderResponseError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Compatibility provider returned an invalid response.",
        ) from error
    except CompatibilityProviderRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    compatibility_check = job_store.save_compatibility_check(
        job_id=job_id,
        snapshot_id=snapshot.id,
        resume_profile_id=resume_profile.id,
        score=evaluation.score,
        decision=evaluation.decision,
        summary=evaluation.summary,
        strengths=evaluation.strengths,
        gaps=evaluation.gaps,
        raw_model_response=evaluation.raw_model_response,
    )
    return RunCompatibilityCheckResponse(
        job_id=job_id,
        compatibility_check=compatibility_check,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> Response:
    was_deleted = job_store.delete_job(job_id)
    if not was_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
