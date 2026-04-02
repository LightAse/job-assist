from fastapi import APIRouter, Depends, HTTPException, status

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.plugins.registry import plugin_registry
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("/scrape-current", response_model=ScrapeCurrentResponse)
def scrape_current(
    payload: ScrapeCurrentRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> ScrapeCurrentResponse:
    plugin = plugin_registry.get_first_match(payload)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No scraper plugin matched the provided input.",
        )

    scrape_result = plugin.scrape(payload)
    job_store.save_matched_scrape(payload, scrape_result)
    return scrape_result
