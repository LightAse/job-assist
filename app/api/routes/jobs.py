import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.schemas.jobs import (
    GenerateJobCvResponse,
    JobDetail,
    JobCheckBatchRun,
    JobListItem,
    RunCandidateCompatibilityCheckResponse,
    RunCompatibilityCheckRequest,
    RunCompatibilityCheckResponse,
    StartJobCheckBatchRequest,
    StoredJob,
    UpdateJobStatusRequest,
)
from app.services.compatibility import get_compatibility_service
from app.services.candidate_compatibility import get_candidate_compatibility_service
from app.services.job_cv_generation import get_job_cv_generation_service
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderRequestError,
    CompatibilityProviderResponseError,
    CompatibilityProviderTimeoutError,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])
_candidate_compatibility_jobs_in_progress: set[int] = set()
_job_cv_generation_jobs_in_progress: set[int] = set()
logger = logging.getLogger(__name__)
_job_check_batch_lock = threading.Lock()
_active_job_check_batch_id: int | None = None
_active_job_check_batch_thread: threading.Thread | None = None

_OPENROUTER_PRIVACY_ERROR_PATTERNS = (
    "no endpoints available matching your guardrail restrictions and data policy",
    "data policy",
    "guardrail restrictions",
)


def _is_openrouter_privacy_policy_error(message: str) -> bool:
    normalized = message.strip().lower()
    return any(pattern in normalized for pattern in _OPENROUTER_PRIVACY_ERROR_PATTERNS)


def _build_provider_request_http_error(error: CompatibilityProviderRequestError) -> HTTPException:
    detail = str(error)
    logger.warning("Compatibility provider request failed: %s", detail)
    if _is_openrouter_privacy_policy_error(detail):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The selected OpenRouter model is unavailable under your current Privacy/Data Policy settings. Check OpenRouter Settings -> Privacy or choose another model.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
    )


def _evaluate_candidate_compatibility_for_job(*, job_id: int, job_store: SQLiteJobStore):
    job = job_store.get_job_detail(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )
    if job.latest_snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No job snapshot is available for compatibility checking.",
        )
    try:
        evaluation = get_candidate_compatibility_service().evaluate(job=job, job_store=job_store)
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
        raise _build_provider_request_http_error(error) from error

    compatibility_check = job_store.save_candidate_compatibility_check(
        job_id=job_id,
        snapshot_id=job.latest_snapshot.id,
        score=evaluation.score,
        short_reason=evaluation.short_reason,
        strengths=evaluation.strengths,
        gaps=evaluation.gaps,
        raw_model_response=evaluation.raw_model_response,
    )
    return compatibility_check


def _is_systemic_provider_failure(detail: str) -> bool:
    normalized = detail.strip().lower()
    return "provider" in normalized or "openrouter" in normalized or "privacy/data policy" in normalized


def _finalize_active_batch(batch_id: int | None) -> None:
    global _active_job_check_batch_id, _active_job_check_batch_thread
    with _job_check_batch_lock:
        if _active_job_check_batch_id == batch_id:
            _active_job_check_batch_id = None
            _active_job_check_batch_thread = None


def _run_job_check_batch_worker(*, database_path: str, batch_id: int) -> None:
    job_store = SQLiteJobStore(database_path)
    batch = job_store.get_job_check_batch(batch_id)
    if batch is None:
        _finalize_active_batch(batch_id)
        return

    consecutive_failure_count = 0
    consecutive_failure_detail: str | None = None
    final_status = "completed"
    last_error = None

    try:
        for item in batch.items:
            job_store.update_job_check_batch_item(batch_id=batch_id, job_id=item.job_id, status_value="running")
            _candidate_compatibility_jobs_in_progress.add(item.job_id)
            try:
                _evaluate_candidate_compatibility_for_job(job_id=item.job_id, job_store=job_store)
                job_store.update_job_check_batch_item(batch_id=batch_id, job_id=item.job_id, status_value="completed")
                consecutive_failure_count = 0
                consecutive_failure_detail = None
            except HTTPException as error:
                detail = str(error.detail)
                job_store.update_job_check_batch_item(
                    batch_id=batch_id,
                    job_id=item.job_id,
                    status_value="failed",
                    error_message=detail,
                )
                if error.status_code == status.HTTP_502_BAD_GATEWAY and _is_systemic_provider_failure(detail):
                    if detail == consecutive_failure_detail:
                        consecutive_failure_count += 1
                    else:
                        consecutive_failure_detail = detail
                        consecutive_failure_count = 1
                    if consecutive_failure_count >= 3:
                        final_status = "failed"
                        last_error = "Batch stopped because the current model/provider is failing consistently."
                        break
                else:
                    consecutive_failure_count = 0
                    consecutive_failure_detail = None
            finally:
                _candidate_compatibility_jobs_in_progress.discard(item.job_id)
        job_store.complete_job_check_batch(batch_id=batch_id, status_value=final_status, last_error=last_error)
    except Exception as error:  # pragma: no cover - defensive guard for worker
        logger.exception("Job check batch worker crashed for batch %s", batch_id)
        job_store.complete_job_check_batch(batch_id=batch_id, status_value="failed", last_error=str(error))
    finally:
        _finalize_active_batch(batch_id)


@router.get("", response_model=list[JobListItem])
def list_jobs(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[JobListItem]:
    return job_store.list_jobs()


@router.post("/check-batch", response_model=JobCheckBatchRun)
def start_job_check_batch(
    payload: StartJobCheckBatchRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> JobCheckBatchRun:
    global _active_job_check_batch_id, _active_job_check_batch_thread
    with _job_check_batch_lock:
        if _active_job_check_batch_id is not None:
            active_batch = job_store.get_job_check_batch(_active_job_check_batch_id)
            if active_batch is not None and active_batch.status == "running":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A job compatibility batch is already running.",
                )
            _active_job_check_batch_id = None
            _active_job_check_batch_thread = None

        jobs = job_store.list_jobs()
        if payload.mode == "unscored":
            jobs = [job for job in jobs if job.latest_candidate_compatibility_check is None]
        job_ids = [job.id for job in jobs]
        batch = job_store.create_job_check_batch(mode=payload.mode, job_ids=job_ids)
        worker = threading.Thread(
            target=_run_job_check_batch_worker,
            kwargs={"database_path": str(job_store.database_path), "batch_id": batch.id},
            daemon=True,
            name=f"job-check-batch-{batch.id}",
        )
        _active_job_check_batch_id = batch.id
        _active_job_check_batch_thread = worker
        worker.start()
        return batch


@router.get("/check-batch/current", response_model=JobCheckBatchRun | None)
def get_current_job_check_batch(job_store: SQLiteJobStore = Depends(get_job_store)) -> JobCheckBatchRun | None:
    batch = job_store.get_current_or_latest_job_check_batch()
    global _active_job_check_batch_id, _active_job_check_batch_thread
    if batch is not None and batch.status == "running":
        with _job_check_batch_lock:
            if _active_job_check_batch_id != batch.id or _active_job_check_batch_thread is None or not _active_job_check_batch_thread.is_alive():
                job_store.complete_job_check_batch(
                    batch_id=batch.id,
                    status_value="failed",
                    last_error="Batch worker stopped before completion.",
                )
                _active_job_check_batch_id = None
                _active_job_check_batch_thread = None
                batch = job_store.get_job_check_batch(batch.id)
    return batch


@router.get("/check-batch/{batch_id}", response_model=JobCheckBatchRun)
def get_job_check_batch(batch_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> JobCheckBatchRun:
    batch = job_store.get_job_check_batch(batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job check batch not found.",
        )
    return batch


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> JobDetail:
    job = job_store.get_job_detail(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )
    return job


@router.put("/{job_id}/status", response_model=StoredJob)
def update_job_status(
    job_id: int,
    payload: UpdateJobStatusRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> StoredJob:
    job = job_store.update_job_status(job_id, payload.status)
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
        raise _build_provider_request_http_error(error) from error

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


@router.post("/{job_id}/candidate-compatibility-check", response_model=RunCandidateCompatibilityCheckResponse)
def run_candidate_compatibility_check(
    job_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> RunCandidateCompatibilityCheckResponse:
    if job_id in _candidate_compatibility_jobs_in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A compatibility check is already running for this job.",
        )
    _candidate_compatibility_jobs_in_progress.add(job_id)
    try:
        compatibility_check = _evaluate_candidate_compatibility_for_job(job_id=job_id, job_store=job_store)
        return RunCandidateCompatibilityCheckResponse(
            job_id=job_id,
            compatibility_check=compatibility_check,
        )
    finally:
        _candidate_compatibility_jobs_in_progress.discard(job_id)


@router.post("/{job_id}/generate-cv", response_model=GenerateJobCvResponse)
def generate_job_cv(
    job_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> GenerateJobCvResponse:
    if job_id in _job_cv_generation_jobs_in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CV generation is already running for this job.",
        )

    job = job_store.get_job_detail(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    _job_cv_generation_jobs_in_progress.add(job_id)
    try:
        artifact = get_job_cv_generation_service().generate_cv(job=job, job_store=job_store)
        return GenerateJobCvResponse(job_id=job_id, artifact=artifact)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except CompatibilityProviderConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error
    except CompatibilityProviderTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="CV generation timed out.",
        ) from error
    except CompatibilityProviderResponseError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except CompatibilityProviderRequestError as error:
        raise _build_provider_request_http_error(error) from error
    finally:
        _job_cv_generation_jobs_in_progress.discard(job_id)


@router.get("/generated-cvs/{artifact_id}/download")
def download_generated_cv(
    artifact_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> FileResponse:
    artifact = job_store.get_generated_cv_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated CV not found.",
        )
    return FileResponse(
        artifact.file_path,
        media_type="text/markdown; charset=utf-8",
        filename=artifact.filename,
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
