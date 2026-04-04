from typing import Any

from pydantic import BaseModel, ConfigDict, HttpUrl


class ScrapeContext(BaseModel):
    url: HttpUrl
    title: str | None = None
    company: str | None = None
    location: str | None = None
    html: str | None = None
    visible_text: str | None = None
    linkedin_job_id: str | None = None


class ScrapeCurrentRequest(ScrapeContext):
    pass


class ScrapeCurrentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugin_name: str
    matched: bool
    source_url: HttpUrl
    raw_content: str | None
    structured_data: dict[str, Any]
    status: str | None = None
    job_id: int | None = None
    deduplicated: bool | None = None
    reason: str | None = None
