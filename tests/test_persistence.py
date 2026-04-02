from pathlib import Path

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


def test_save_matched_scrape_persists_job_snapshot_and_resume_check_data(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_persistence.db")
    context = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/1234567890/",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
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
    profile = store.create_resume_profile(
        name="Backend Resume",
        content="Python FastAPI SQL backend engineer",
    )
    compatibility_check = store.save_compatibility_check(
        job_id=record.job_id,
        snapshot_id=record.snapshot_id,
        resume_profile_id=profile.id,
        score=78,
        decision="strong_match",
        summary="Good overlap on the main backend keywords.",
        strengths=["Resume references Python.", "Resume references FastAPI."],
        gaps=["Job snapshot mentions LinkedIn-specific details not present in the resume."],
        raw_model_response='{"method":"keyword_overlap_v1"}',
    )

    with store._connect() as connection:
        job_row = connection.execute("SELECT * FROM jobs WHERE id = ?", (record.job_id,)).fetchone()
        snapshot_row = connection.execute(
            "SELECT * FROM job_snapshots WHERE id = ?",
            (record.snapshot_id,),
        ).fetchone()
        profile_row = connection.execute(
            "SELECT * FROM resume_profiles WHERE id = ?",
            (profile.id,),
        ).fetchone()
        compatibility_row = connection.execute(
            "SELECT * FROM compatibility_checks WHERE id = ?",
            (compatibility_check.id,),
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
    assert snapshot_row["company"] == "Example Co"
    assert snapshot_row["location"] == "Remote"
    assert snapshot_row["html"] == "<html>job page</html>"
    assert snapshot_row["visible_text"] == "Senior Backend Engineer at Example Co"
    assert snapshot_row["plugin_name"] == "linkedin_job_scraper"

    assert profile_row is not None
    assert profile_row["name"] == "Backend Resume"
    assert profile_row["content"] == "Python FastAPI SQL backend engineer"

    assert compatibility_row is not None
    assert compatibility_row["job_id"] == record.job_id
    assert compatibility_row["snapshot_id"] == record.snapshot_id
    assert compatibility_row["resume_profile_id"] == profile.id
    assert compatibility_row["score"] == 78
    assert compatibility_row["decision"] == "strong_match"


def test_delete_job_removes_job_snapshots_and_compatibility_checks(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_delete_persistence.db")
    context = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/1234567890/",
        title="Senior Backend Engineer",
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
    profile = store.create_resume_profile(
        name="Backend Resume",
        content="Python FastAPI SQL backend engineer",
    )
    store.save_compatibility_check(
        job_id=record.job_id,
        snapshot_id=record.snapshot_id,
        resume_profile_id=profile.id,
        score=55,
        decision="borderline",
        summary="Some overlap on the main backend keywords.",
        strengths=["Resume references Python."],
        gaps=["Job snapshot mentions SQL explicitly."],
        raw_model_response='{"method":"keyword_overlap_v1"}',
    )

    assert store.delete_job(record.job_id) is True

    with store._connect() as connection:
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        snapshots_count = connection.execute("SELECT COUNT(*) FROM job_snapshots").fetchone()[0]
        checks_count = connection.execute("SELECT COUNT(*) FROM compatibility_checks").fetchone()[0]
        profiles_count = connection.execute("SELECT COUNT(*) FROM resume_profiles").fetchone()[0]

    assert jobs_count == 0
    assert snapshots_count == 0
    assert checks_count == 0
    assert profiles_count == 1
