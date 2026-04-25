from pathlib import Path

import pytest
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

    assert response.model_dump(mode="json", exclude_none=True) == {
        "plugin_name": "linkedin_job_scraper",
        "matched": True,
        "source_url": "https://www.linkedin.com/jobs/view/1234567890/",
        "structured_data": {
            "external_job_id": "1234567890",
            "page_title": "Senior Backend Engineer",
            "source": "linkedin",
        },
        "status": "created",
        "job_id": 1,
        "deduplicated": False,
    }


def test_scrape_current_returns_linkedin_plugin_response_for_search_results_current_job(temp_job_store: SQLiteJobStore) -> None:
    response = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/search-results/?currentJobId=1234567890",
            title="Senior Backend Engineer",
            company="Example Co",
            visible_text="Senior Backend Engineer at Example Co",
            linkedin_job_id="1234567890",
        ),
        job_store=temp_job_store,
    )

    assert response.plugin_name == "linkedin_job_scraper"
    assert response.status == "created"
    assert response.deduplicated is False
    assert response.structured_data["external_job_id"] == "1234567890"
    assert response.structured_data["source"] == "linkedin"


def test_scrape_current_returns_generic_plugin_response_for_non_matching_url(temp_job_store: SQLiteJobStore) -> None:
    response = scrape_current(
        ScrapeCurrentRequest(
            url="https://jobs.example.com/openings/backend-engineer-987654",
            title="Backend Engineer | Example",
            visible_text="Backend Engineer at Example",
        ),
        job_store=temp_job_store,
    )

    assert response.model_dump(mode="json", exclude_none=True) == {
        "plugin_name": "generic_job_capture",
        "matched": True,
        "source_url": "https://jobs.example.com/openings/backend-engineer-987654",
        "structured_data": {
            "external_job_id": "987654",
            "page_title": "Backend Engineer | Example",
            "source": "generic",
            "tentative_job_title": "Backend Engineer",
        },
        "status": "created",
        "job_id": 1,
        "deduplicated": False,
    }


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
    assert response.status == "created"
    assert response.deduplicated is False


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
    assert response.status == "created"
    assert response.deduplicated is False

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


def test_scrape_current_persists_generic_result(temp_job_store: SQLiteJobStore) -> None:
    response = scrape_current(
        ScrapeCurrentRequest(
            url="https://boards.greenhouse.io/acme/jobs/7654321",
            title="Platform Engineer",
            company="Acme",
            location="Remote",
            visible_text="Platform Engineer at Acme",
        ),
        job_store=temp_job_store,
    )

    with temp_job_store._connect() as connection:
        job_row = connection.execute("SELECT * FROM jobs").fetchone()
        snapshot_row = connection.execute("SELECT * FROM job_snapshots").fetchone()

    assert response.plugin_name == "generic_job_capture"
    assert response.status == "created"
    assert response.deduplicated is False
    assert job_row is not None
    assert job_row["source"] == "greenhouse"
    assert job_row["external_job_id"] == "7654321"
    assert snapshot_row is not None
    assert snapshot_row["company"] == "Acme"
    assert snapshot_row["location"] == "Remote"


def test_scrape_current_skips_duplicate_linkedin_job(temp_job_store: SQLiteJobStore) -> None:
    first = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/collections/recommended/?currentJobId=1234567890",
            title="Senior Backend Engineer",
            company="Example Co",
            visible_text="Senior Backend Engineer at Example Co",
            linkedin_job_id="1234567890",
        ),
        job_store=temp_job_store,
    )
    second = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/collections/recommended/?currentJobId=1234567890",
            title="Senior Backend Engineer",
            company="Example Co",
            visible_text="Senior Backend Engineer at Example Co",
            linkedin_job_id="1234567890",
        ),
        job_store=temp_job_store,
    )

    with temp_job_store._connect() as connection:
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        snapshots_count = connection.execute("SELECT COUNT(*) FROM job_snapshots").fetchone()[0]

    assert first.status == "created"
    assert first.deduplicated is False
    assert second.status == "skipped"
    assert second.deduplicated is True
    assert second.reason == "duplicate"
    assert second.job_id == first.job_id
    assert jobs_count == 1
    assert snapshots_count == 1


def test_scrape_current_creates_new_rows_for_distinct_jobs(temp_job_store: SQLiteJobStore) -> None:
    first = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/1234567890/",
            title="Senior Backend Engineer",
            company="Example Co",
            visible_text="Senior Backend Engineer at Example Co",
        ),
        job_store=temp_job_store,
    )
    second = scrape_current(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/9876543210/",
            title="Staff Backend Engineer",
            company="Example Co",
            visible_text="Staff Backend Engineer at Example Co",
        ),
        job_store=temp_job_store,
    )

    with temp_job_store._connect() as connection:
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    assert first.status == "created"
    assert second.status == "created"
    assert first.job_id != second.job_id
    assert jobs_count == 2
