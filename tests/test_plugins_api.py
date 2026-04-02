from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.plugins import scrape_current
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.scrape import ScrapeCurrentRequest


@pytest.fixture
def temp_job_store(tmp_path: Path) -> SQLiteJobStore:
    return SQLiteJobStore(tmp_path / "test_api.db")


def test_scrape_current_returns_linkedin_plugin_response(temp_job_store: SQLiteJobStore) -> None:
    response = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/1234567890/",
            title="Senior Backend Engineer",
        ),
        job_store=temp_job_store,
    )

    assert response.model_dump(mode="json") == {
        "plugin_name": "linkedin_job_scraper",
        "matched": True,
        "source_url": "https://www.linkedin.com/jobs/view/1234567890/",
        "raw_content": None,
        "structured_data": {
            "external_job_id": "1234567890",
            "page_title": "Senior Backend Engineer",
            "source": "linkedin",
        },
    }


def test_scrape_current_returns_404_for_non_matching_url(temp_job_store: SQLiteJobStore) -> None:
    with pytest.raises(HTTPException) as error:
        scrape_current(
            ScrapeCurrentRequest(
                url="https://example.com/jobs/1234567890",
                title="Example role",
            ),
            job_store=temp_job_store,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "No scraper plugin matched the provided input."


def test_scrape_current_accepts_html_and_visible_text_context(temp_job_store: SQLiteJobStore) -> None:
    response = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/1234567890/",
            html="<html><body><h1>Senior Backend Engineer</h1></body></html>",
            visible_text="Senior Backend Engineer at Example Co",
        ),
        job_store=temp_job_store,
    )

    assert response.structured_data == {
        "external_job_id": "1234567890",
        "source": "linkedin",
        "tentative_job_title": "Senior Backend Engineer",
    }


def test_scrape_current_persists_matched_result(temp_job_store: SQLiteJobStore) -> None:
    response = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/1234567890/",
            title="Senior Backend Engineer",
            visible_text="Senior Backend Engineer at Example Co",
        ),
        job_store=temp_job_store,
    )

    assert response.plugin_name == "linkedin_job_scraper"

    with temp_job_store._connect() as connection:
        job_row = connection.execute("SELECT * FROM jobs").fetchone()
        snapshot_row = connection.execute("SELECT * FROM job_snapshots").fetchone()

    assert job_row is not None
    assert job_row["source"] == "linkedin"
    assert job_row["external_job_id"] == "1234567890"
    assert job_row["source_url"] == "https://www.linkedin.com/jobs/view/1234567890/"
    assert job_row["page_title"] == "Senior Backend Engineer"
    assert job_row["tentative_job_title"] == "Senior Backend Engineer"

    assert snapshot_row is not None
    assert snapshot_row["job_id"] == job_row["id"]
    assert snapshot_row["plugin_name"] == "linkedin_job_scraper"
    assert snapshot_row["title"] == "Senior Backend Engineer"
    assert snapshot_row["visible_text"] == "Senior Backend Engineer at Example Co"


def test_scrape_current_does_not_persist_non_matching_result(temp_job_store: SQLiteJobStore) -> None:
    with pytest.raises(HTTPException):
        scrape_current(
            ScrapeCurrentRequest(url="https://example.com/jobs/1234567890"),
            job_store=temp_job_store,
        )

    with temp_job_store._connect() as connection:
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        snapshots_count = connection.execute("SELECT COUNT(*) FROM job_snapshots").fetchone()[0]

    assert jobs_count == 0
    assert snapshots_count == 0
