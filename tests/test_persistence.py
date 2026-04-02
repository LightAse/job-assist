from pathlib import Path

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


def test_save_matched_scrape_persists_job_and_snapshot(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_persistence.db")
    context = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/1234567890/",
        title="Senior Backend Engineer",
        html="<html>job page</html>",
        visible_text="Senior Backend Engineer at Example Co",
    )
    scrape_result = ScrapeCurrentResponse(
        plugin_name="linkedin_job_scraper",
        matched=True,
        source_url=context.url,
        raw_content=None,
        structured_data={
            "source": "linkedin",
            "external_job_id": "1234567890",
            "page_title": "Senior Backend Engineer",
            "tentative_job_title": "Senior Backend Engineer",
        },
    )

    record = store.save_matched_scrape(context, scrape_result)

    with store._connect() as connection:
        job_row = connection.execute("SELECT * FROM jobs WHERE id = ?", (record.job_id,)).fetchone()
        snapshot_row = connection.execute(
            "SELECT * FROM job_snapshots WHERE id = ?",
            (record.snapshot_id,),
        ).fetchone()

    assert job_row is not None
    assert job_row["source"] == "linkedin"
    assert job_row["external_job_id"] == "1234567890"
    assert job_row["page_title"] == "Senior Backend Engineer"
    assert job_row["tentative_job_title"] == "Senior Backend Engineer"

    assert snapshot_row is not None
    assert snapshot_row["job_id"] == record.job_id
    assert snapshot_row["source_url"] == "https://www.linkedin.com/jobs/view/1234567890/"
    assert snapshot_row["title"] == "Senior Backend Engineer"
    assert snapshot_row["html"] == "<html>job page</html>"
    assert snapshot_row["visible_text"] == "Senior Backend Engineer at Example Co"
    assert snapshot_row["plugin_name"] == "linkedin_job_scraper"
