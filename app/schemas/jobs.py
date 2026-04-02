from pydantic import BaseModel, HttpUrl


class StoredJob(BaseModel):
    id: int
    source: str
    external_job_id: str | None
    source_url: HttpUrl
    page_title: str | None
    tentative_job_title: str | None
    created_at: str
