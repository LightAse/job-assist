from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.jobs import delete_job, get_job, list_jobs, run_compatibility_check
from app.api.routes.resume_profiles import create_resume_profile, list_resume_profiles
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import CreateResumeProfileRequest, RunCompatibilityCheckRequest
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


@pytest.fixture
def temp_job_store(tmp_path: Path) -> SQLiteJobStore:
    return SQLiteJobStore(tmp_path / "test_jobs_api.db")


def _save_job(
    store: SQLiteJobStore,
    *,
    job_id: str,
    title: str,
    company: str | None = None,
    location: str | None = None,
    visible_text: str | None = None,
    html: str | None = None,
) -> int:
    context = ScrapeCurrentRequest(
        url=f"https://www.linkedin.com/jobs/view/{job_id}/",
        title=title,
        company=company,
        location=location,
        visible_text=visible_text,
        html=html,
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
            "tentative_job_title": visible_text.split(" at ", 1)[0] if visible_text and " at " in visible_text else None,
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


def test_get_job_returns_latest_snapshot_and_latest_check(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Backend Engineer at Example Co\nPython FastAPI SQL",
        html="<html>Backend Engineer</html>",
    )
    resume_profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="Backend Resume",
            content="Python FastAPI SQL Remote backend engineer",
        ),
        job_store=temp_job_store,
    )
    check_response = run_compatibility_check(
        job_id=job_id,
        payload=RunCompatibilityCheckRequest(resume_profile_id=resume_profile.id),
        job_store=temp_job_store,
    )

    job = get_job(job_id=job_id, job_store=temp_job_store)

    assert job.id == job_id
    assert job.latest_snapshot is not None
    assert job.latest_snapshot.title == "Backend Engineer"
    assert job.latest_snapshot.company == "Example Co"
    assert job.latest_snapshot.location == "Remote"
    assert job.latest_snapshot.visible_text == "Backend Engineer at Example Co\nPython FastAPI SQL"
    assert job.latest_snapshot.html == "<html>Backend Engineer</html>"
    assert job.latest_snapshot.plugin_name == "linkedin_job_scraper"
    assert job.latest_compatibility_check is not None
    assert job.latest_compatibility_check.id == check_response.compatibility_check.id
    assert job.latest_compatibility_check.resume_profile_id == resume_profile.id
    assert job.latest_compatibility_check.score >= 0


def test_run_compatibility_check_persists_result(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres Remote",
    )
    resume_profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="Senior Backend Resume",
            content="Senior backend engineer with Python FastAPI Postgres experience in remote teams.",
        ),
        job_store=temp_job_store,
    )

    response = run_compatibility_check(
        job_id=job_id,
        payload=RunCompatibilityCheckRequest(resume_profile_id=resume_profile.id),
        job_store=temp_job_store,
    )

    assert response.job_id == job_id
    assert response.compatibility_check.resume_profile_id == resume_profile.id
    assert response.compatibility_check.decision in {"strong_match", "borderline", "weak_match"}
    assert response.compatibility_check.summary
    assert response.compatibility_check.strengths
    assert response.compatibility_check.gaps
    assert '"method": "keyword_overlap_v1"' in response.compatibility_check.raw_model_response


def test_run_compatibility_check_raises_404_for_missing_resume_profile(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Backend Engineer",
    )

    with pytest.raises(HTTPException) as error:
        run_compatibility_check(
            job_id=job_id,
            payload=RunCompatibilityCheckRequest(resume_profile_id=9999),
            job_store=temp_job_store,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Resume profile not found."


def test_get_job_raises_404_for_missing_job(temp_job_store: SQLiteJobStore) -> None:
    with pytest.raises(HTTPException) as error:
        get_job(job_id=9999, job_store=temp_job_store)

    assert error.value.status_code == 404
    assert error.value.detail == "Job not found."


def test_delete_job_removes_one_stored_job(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Backend Engineer",
    )

    response = delete_job(job_id=job_id, job_store=temp_job_store)

    assert response.status_code == 204
    assert temp_job_store.get_job(job_id) is None


def test_delete_job_raises_404_for_missing_job(temp_job_store: SQLiteJobStore) -> None:
    with pytest.raises(HTTPException) as error:
        delete_job(job_id=9999, job_store=temp_job_store)

    assert error.value.status_code == 404
    assert error.value.detail == "Job not found."


def test_resume_profile_routes_create_and_list_profiles(temp_job_store: SQLiteJobStore) -> None:
    created_profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="General Resume",
            content="Backend engineer with Python and SQL experience.",
        ),
        job_store=temp_job_store,
    )

    profiles = list_resume_profiles(job_store=temp_job_store)

    assert created_profile.id > 0
    assert [profile.id for profile in profiles] == [created_profile.id]
    assert profiles[0].name == "General Resume"
