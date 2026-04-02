from fastapi import APIRouter, Depends, status

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.schemas.jobs import CreateResumeProfileRequest, ResumeProfile


router = APIRouter(prefix="/resume-profiles", tags=["resume-profiles"])


@router.get("", response_model=list[ResumeProfile])
def list_resume_profiles(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[ResumeProfile]:
    return job_store.list_resume_profiles()


@router.post("", response_model=ResumeProfile, status_code=status.HTTP_201_CREATED)
def create_resume_profile(
    payload: CreateResumeProfileRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> ResumeProfile:
    return job_store.create_resume_profile(name=payload.name, content=payload.content)
