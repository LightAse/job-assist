from typing import Any

from pydantic import BaseModel, HttpUrl


class ScrapeContext(BaseModel):
    url: HttpUrl
    title: str | None = None
    html: str | None = None
    visible_text: str | None = None


class ScrapeCurrentRequest(ScrapeContext):
    pass


class ScrapeCurrentResponse(BaseModel):
    plugin_name: str
    matched: bool
    source_url: HttpUrl
    raw_content: str | None
    structured_data: dict[str, Any]
