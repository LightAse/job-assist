from pydantic import BaseModel, HttpUrl


class StoredJob(BaseModel):
    id: int
    source: str
    external_job_id: str | None
    source_url: HttpUrl
    page_title: str | None
    tentative_job_title: str | None
    created_at: str


class LatestJobSnapshot(BaseModel):
    id: int
    title: str | None
    company: str | None
    location: str | None
    visible_text: str | None
    html: str | None
    plugin_name: str
    captured_at: str


class CompatibilityCheckResult(BaseModel):
    id: int
    resume_profile_id: int
    score: int
    decision: str
    summary: str
    strengths: list[str]
    gaps: list[str]
    raw_model_response: str
    created_at: str


class JobDetail(StoredJob):
    latest_snapshot: LatestJobSnapshot | None
    latest_compatibility_check: CompatibilityCheckResult | None


class ResumeProfile(BaseModel):
    id: int
    name: str
    content: str
    created_at: str


class CreateResumeProfileRequest(BaseModel):
    name: str
    content: str


class RunCompatibilityCheckRequest(BaseModel):
    resume_profile_id: int


class RunCompatibilityCheckResponse(BaseModel):
    job_id: int
    compatibility_check: CompatibilityCheckResult
