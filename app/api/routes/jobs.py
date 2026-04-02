from fastapi import APIRouter, Depends, HTTPException, status

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.schemas.jobs import StoredJob


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[StoredJob])
def list_jobs(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[StoredJob]:
    return job_store.list_jobs()


@router.get("/{job_id}", response_model=StoredJob)
def get_job(job_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> StoredJob:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )
    return job
