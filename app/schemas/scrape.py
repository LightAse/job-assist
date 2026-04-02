from typing import Any

from pydantic import BaseModel, HttpUrl


class ScrapeCurrentRequest(BaseModel):
    url: HttpUrl


class ScrapeCurrentResponse(BaseModel):
    plugin_name: str
    matched: bool
    source_url: HttpUrl
    raw_content: str | None
    structured_data: dict[str, Any]
