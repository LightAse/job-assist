from fastapi import APIRouter, HTTPException, status

from app.plugins.registry import plugin_registry
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("/scrape-current", response_model=ScrapeCurrentResponse)
def scrape_current(payload: ScrapeCurrentRequest) -> ScrapeCurrentResponse:
    plugin = plugin_registry.get_first_match(payload)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No scraper plugin matched the provided input.",
        )

    return plugin.scrape(payload)
