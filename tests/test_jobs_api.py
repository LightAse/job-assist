from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.jobs import (
    download_generated_cv,
    delete_job,
    generate_job_cv,
    get_job,
    list_jobs,
    run_candidate_compatibility_check,
    run_compatibility_check,
    update_job_status,
)
from app.api.routes.resume_profiles import create_resume_profile, list_resume_profiles
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import (
    CreateMasterSkillRequest,
    CreateMasterWorkExperienceRequest,
    CreateResumeProfileRequest,
    RunCompatibilityCheckRequest,
    UpdateCandidateProfileRequest,
    UpdateJobStatusRequest,
)
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse
from app.services.compatibility_errors import CompatibilityProviderRequestError


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
        company="Example Co",
    )

    jobs = list_jobs(job_store=temp_job_store)

    assert [job.id for job in jobs] == [newer_job_id, older_job_id]
    assert jobs[0].external_job_id == "9876543210"
    assert jobs[0].latest_snapshot is not None
    assert jobs[0].latest_snapshot.title == "Senior Backend Engineer"
    assert jobs[0].latest_snapshot.company == "Example Co"
    assert jobs[0].status == "new"
    assert jobs[1].external_job_id == "1234567890"
    assert jobs[1].status == "new"


def test_update_job_status_persists_and_is_returned_by_list_and_detail(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Backend Engineer",
        company="Example Co",
    )

    updated_job = update_job_status(
        job_id=job_id,
        payload=UpdateJobStatusRequest(status="in_progress"),
        job_store=temp_job_store,
    )

    assert updated_job.status == "in_progress"

    job = get_job(job_id=job_id, job_store=temp_job_store)
    jobs = list_jobs(job_store=temp_job_store)

    assert job.status == "in_progress"
    assert jobs[0].status == "in_progress"


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


def test_run_candidate_compatibility_check_persists_result(temp_job_store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres Remote",
    )
    temp_job_store.update_candidate_profile(type("Payload", (), {"summary": "Backend engineer with Python and FastAPI experience."})())

    class FakeService:
        def evaluate(self, *, job, job_store):
            return type(
                "Result",
                (),
                {
                    "score": 82,
                    "short_reason": "Strong backend overlap with some infrastructure gaps.",
                    "strengths": ["Python", "FastAPI"],
                    "gaps": ["AWS"],
                    "raw_model_response": '{"score":82}',
                },
            )()

    monkeypatch.setattr("app.api.routes.jobs.get_candidate_compatibility_service", lambda: FakeService())

    response = run_candidate_compatibility_check(job_id=job_id, job_store=temp_job_store)

    assert response.job_id == job_id
    assert response.compatibility_check.score == 82
    assert response.compatibility_check.short_reason

    job = get_job(job_id=job_id, job_store=temp_job_store)
    assert job.latest_candidate_compatibility_check is not None
    assert job.latest_candidate_compatibility_check.score == 82

    jobs = list_jobs(job_store=temp_job_store)
    assert jobs[0].latest_candidate_compatibility_check is not None
    assert jobs[0].latest_candidate_compatibility_check.score == 82


def test_run_candidate_compatibility_check_persists_job_run(
    temp_job_store: SQLiteJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="7777777777",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres Remote",
    )
    temp_job_store.update_candidate_profile(type("Payload", (), {"summary": "Backend engineer with Python and FastAPI experience."})())

    class FakeService:
        def evaluate(self, *, job, job_store):
            return type(
                "Result",
                (),
                {
                    "score": 75,
                    "short_reason": "Relevant backend skills match the role.",
                    "strengths": ["Python"],
                    "gaps": ["AWS"],
                    "raw_model_response": '{"score":75}',
                },
            )()

    monkeypatch.setattr("app.api.routes.jobs.get_candidate_compatibility_service", lambda: FakeService())

    response = run_candidate_compatibility_check(job_id=job_id, job_store=temp_job_store)

    with temp_job_store._connect() as connection:
        run_row = connection.execute(
            """
            SELECT job_type, target_job_id, status, started_at, finished_at
            FROM job_runs
            WHERE target_job_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()

    assert response.compatibility_check.score == 75
    assert run_row is not None
    assert run_row["job_type"] == "candidate_compatibility_check"
    assert run_row["target_job_id"] == job_id
    assert run_row["status"] == "completed"
    assert run_row["started_at"] is not None
    assert run_row["finished_at"] is not None


def test_run_candidate_compatibility_check_maps_openrouter_privacy_error_to_clear_message(
    temp_job_store: SQLiteJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres Remote",
    )

    class FakeService:
        def evaluate(self, *, job, job_store):
            raise CompatibilityProviderRequestError(
                "No endpoints available matching your guardrail restrictions and data policy"
            )

    monkeypatch.setattr("app.api.routes.jobs.get_candidate_compatibility_service", lambda: FakeService())

    with pytest.raises(HTTPException) as error:
        run_candidate_compatibility_check(job_id=job_id, job_store=temp_job_store)

    assert error.value.status_code == 502
    assert error.value.detail == (
        "The selected OpenRouter model is unavailable under your current Privacy/Data Policy settings. "
        "Check OpenRouter Settings -> Privacy or choose another model."
    )


def test_generate_job_cv_persists_artifact_and_exposes_download(
    temp_job_store: SQLiteJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _save_job(
        temp_job_store,
        job_id="1234567890",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres",
    )
    temp_job_store.update_candidate_profile(
        UpdateCandidateProfileRequest(
            full_name="Jane Doe",
            email="jane@example.com",
            phone="+1 555 010 1234",
            location="Austin, TX",
            linkedin_url="https://linkedin.com/in/jane",
            summary="Backend engineer with Python API experience.",
        )
    )
    temp_job_store.create_master_skill(CreateMasterSkillRequest(name="Python", proficiency_level="Advanced"))
    temp_job_store.create_master_work_experience(
        CreateMasterWorkExperienceRequest(
            company="Previous Co",
            title="Backend Engineer",
            summary="Built Python APIs.",
            highlights=["Built FastAPI services", "Worked with Postgres"],
        )
    )

    class FakeGenerator:
        def generate_summary_from_sources(self, **kwargs):
            return "Backend engineer focused on Python API delivery for distributed teams."

        def generate_skills_from_sources(self, **kwargs):
            return ["Python", "FastAPI", "Postgres"]

    monkeypatch.setattr("app.services.job_cv_generation.get_summary_generation_service", lambda: FakeGenerator())

    response = generate_job_cv(job_id=job_id, job_store=temp_job_store)

    assert response.job_id == job_id
    assert response.artifact.filename == f"jane_doe_cv_example_co_{job_id}.md"
    assert Path(response.artifact.file_path).exists()

    job = get_job(job_id=job_id, job_store=temp_job_store)
    assert job.generated_cvs
    assert job.generated_cvs[0].id == response.artifact.id

    download_response = download_generated_cv(response.artifact.id, job_store=temp_job_store)
    assert download_response.filename == response.artifact.filename


def test_generate_job_cv_requires_candidate_personal_data(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(temp_job_store)

    with pytest.raises(HTTPException) as error:
        generate_job_cv(job_id=job_id, job_store=temp_job_store)

    assert error.value.status_code == 400
    assert error.value.detail == "Candidate Data is missing required fields: full name, email, phone, location."


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
