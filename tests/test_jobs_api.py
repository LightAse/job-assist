from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.jobs import get_job, list_jobs
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


@pytest.fixture
def temp_job_store(tmp_path: Path) -> SQLiteJobStore:
    return SQLiteJobStore(tmp_path / "test_jobs_api.db")


def _save_job(
    store: SQLiteJobStore,
    *,
    job_id: str,
    title: str,
    visible_text: str | None = None,
) -> int:
    context = ScrapeCurrentRequest(
        url=f"https://www.linkedin.com/jobs/view/{job_id}/",
        title=title,
        visible_text=visible_text,
    )
    result = ScrapeCurrentResponse(
        plugin_name="linkedin_job_scraper",
        matched=True,
        source_url=context.url,
        raw_content=None,
        structured_data={
            "source": "linkedin",
            "external_job_id": job_id,
            "page_title": title,
            "tentative_job_title": visible_text.split(" at ", 1)[0] if visible_text else None,
        },
    )
    return store.save_matched_scrape(context, result).job_id


def test_list_jobs_returns_newest_first(temp_job_store: SQLiteJobStore) -> None:
    older_job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Backend Engineer",
    )
    newer_job_id = _save_job(
        temp_job_store,
        job_id="9876543210",
        title="Senior Backend Engineer",
    )

    jobs = list_jobs(job_store=temp_job_store)

    assert [job.id for job in jobs] == [newer_job_id, older_job_id]
    assert jobs[0].external_job_id == "9876543210"
    assert jobs[1].external_job_id == "1234567890"


def test_get_job_returns_one_stored_job(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Backend Engineer",
        visible_text="Backend Engineer at Example Co",
    )

    job = get_job(job_id=job_id, job_store=temp_job_store)

    assert job.id == job_id
    assert job.source == "linkedin"
    assert job.external_job_id == "1234567890"
    assert str(job.source_url) == "https://www.linkedin.com/jobs/view/1234567890/"
    assert job.page_title == "Backend Engineer"
    assert job.tentative_job_title == "Backend Engineer"


def test_get_job_raises_404_for_missing_job(temp_job_store: SQLiteJobStore) -> None:
    with pytest.raises(HTTPException) as error:
        get_job(job_id=9999, job_store=temp_job_store)

    assert error.value.status_code == 404
    assert error.value.detail == "Job not found."
