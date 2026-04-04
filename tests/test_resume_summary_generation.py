from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.resume_profiles import (
    create_resume_profile,
    generate_resume_skills,
    generate_resume_summary,
)
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import (
    CreateResumeProfileRequest,
    GenerateResumeSkillsRequest,
    GenerateResumeSummaryRequest,
    UpdatePromptSettingsRequest,
)
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse
from app.services.compatibility_openrouter import OpenRouterCompatibilityProvider
from app.services.compatibility_errors import CompatibilityProviderResponseError
from app.services.resume_summary_generation import OpenRouterSummaryGenerationService


@pytest.fixture
def temp_job_store(tmp_path: Path) -> SQLiteJobStore:
    return SQLiteJobStore(tmp_path / "test_resume_summary_generation.db")


def _save_job(store: SQLiteJobStore, job_id: str = "1234567890") -> int:
    context = ScrapeCurrentRequest(
        url=f"https://www.linkedin.com/jobs/view/{job_id}/",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres Remote",
    )
    result = ScrapeCurrentResponse(
        plugin_name="linkedin_job_scraper",
        matched=True,
        source_url=context.url,
        raw_content=None,
        structured_data={
            "source": "linkedin",
            "external_job_id": job_id,
            "page_title": "Senior Backend Engineer",
            "tentative_job_title": "Senior Backend Engineer",
        },
    )
    return store.save_matched_scrape(context, result).job_id


def test_generate_resume_summary_success_persists_generated_content(
    monkeypatch: pytest.MonkeyPatch,
    temp_job_store: SQLiteJobStore,
) -> None:
    job_id = _save_job(temp_job_store)
    temp_job_store.update_candidate_profile(type("Payload", (), {"summary": "Experienced backend engineer."})())
    profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="Backend Resume",
            headline="Backend Engineer",
            summary="Source guidance",
        ),
        job_store=temp_job_store,
    )

    class FakeService:
        def generate_summary(self, *, job, resume_profile, job_store):
            job_store.save_resume_profile_section_generation(
                resume_profile_id=resume_profile.id,
                section_key="summary",
                generated_content="Backend engineer with strong Python and FastAPI experience aligned to remote platform roles.",
            )
            return type(
                "Result",
                (),
                {
                    "generated_summary": "Backend engineer with strong Python and FastAPI experience aligned to remote platform roles."
                },
            )()

    monkeypatch.setattr("app.api.routes.resume_profiles.get_summary_generation_service", lambda: FakeService())

    response = generate_resume_summary(
        resume_profile_id=profile.id,
        payload=GenerateResumeSummaryRequest(job_id=job_id, resume_profile_id=profile.id),
        job_store=temp_job_store,
    )

    assert response.job_id == job_id
    assert "Python and FastAPI" in response.generated_summary
    updated_profile = temp_job_store.get_resume_profile_detail(profile.id)
    summary_section = next(section for section in updated_profile.sections if section.section_key == "summary")
    assert summary_section.generated_content == response.generated_summary
    assert summary_section.generated_at is not None


def test_generate_resume_summary_returns_bad_gateway_for_empty_output(
    monkeypatch: pytest.MonkeyPatch,
    temp_job_store: SQLiteJobStore,
) -> None:
    job_id = _save_job(temp_job_store)
    profile = create_resume_profile(
        CreateResumeProfileRequest(name="Backend Resume"),
        job_store=temp_job_store,
    )

    class FakeService:
        def generate_summary(self, *, job, resume_profile, job_store):
            raise CompatibilityProviderResponseError("OpenRouter response did not contain a generated summary.")

    monkeypatch.setattr("app.api.routes.resume_profiles.get_summary_generation_service", lambda: FakeService())

    with pytest.raises(HTTPException) as error:
        generate_resume_summary(
            resume_profile_id=profile.id,
            payload=GenerateResumeSummaryRequest(job_id=job_id, resume_profile_id=profile.id),
            job_store=temp_job_store,
        )

    assert error.value.status_code == 502
    assert error.value.detail == "OpenRouter response did not contain a generated summary."


def test_generate_resume_summary_rejects_invalid_job(temp_job_store: SQLiteJobStore) -> None:
    profile = create_resume_profile(
        CreateResumeProfileRequest(name="Backend Resume"),
        job_store=temp_job_store,
    )

    with pytest.raises(HTTPException) as error:
        generate_resume_summary(
            resume_profile_id=profile.id,
            payload=GenerateResumeSummaryRequest(job_id=9999, resume_profile_id=profile.id),
            job_store=temp_job_store,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Job not found."


def test_generate_resume_summary_rejects_invalid_resume_profile(temp_job_store: SQLiteJobStore) -> None:
    job_id = _save_job(temp_job_store)

    with pytest.raises(HTTPException) as error:
        generate_resume_summary(
            resume_profile_id=9999,
            payload=GenerateResumeSummaryRequest(job_id=job_id, resume_profile_id=9999),
            job_store=temp_job_store,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Resume profile not found."


def test_generate_resume_skills_success_persists_generated_content(
    monkeypatch: pytest.MonkeyPatch,
    temp_job_store: SQLiteJobStore,
) -> None:
    job_id = _save_job(temp_job_store)
    profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="Backend Resume",
            selected_skill_ids=[],
        ),
        job_store=temp_job_store,
    )

    skill = temp_job_store.create_master_skill(
        type("Payload", (), {"name": "FastAPI", "proficiency_level": "Advanced", "notes": "REST APIs"})()
    )
    temp_job_store.update_resume_profile(
        profile.id,
        name="Backend Resume",
        selected_skill_ids=[skill.id],
    )

    class FakeService:
        def generate_skills(self, *, job, resume_profile, job_store):
            job_store.save_resume_profile_section_generation(
                resume_profile_id=resume_profile.id,
                section_key="skills",
                generated_content="- FastAPI\n- Python\n- REST APIs",
            )
            return type("Result", (), {"generated_skills": ["FastAPI", "Python", "REST APIs"]})()

    monkeypatch.setattr("app.api.routes.resume_profiles.get_summary_generation_service", lambda: FakeService())

    response = generate_resume_skills(
        resume_profile_id=profile.id,
        payload=GenerateResumeSkillsRequest(job_id=job_id, resume_profile_id=profile.id),
        job_store=temp_job_store,
    )

    assert response.job_id == job_id
    assert response.generated_skills == ["FastAPI", "Python", "REST APIs"]
    updated_profile = temp_job_store.get_resume_profile_detail(profile.id)
    skills_section = next(section for section in updated_profile.sections if section.section_key == "skills")
    assert skills_section.generated_content == "- FastAPI\n- Python\n- REST APIs"
    assert skills_section.generated_at is not None


def test_generate_resume_skills_returns_bad_gateway_for_empty_output(
    monkeypatch: pytest.MonkeyPatch,
    temp_job_store: SQLiteJobStore,
) -> None:
    job_id = _save_job(temp_job_store)
    profile = create_resume_profile(
        CreateResumeProfileRequest(name="Backend Resume"),
        job_store=temp_job_store,
    )

    class FakeService:
        def generate_skills(self, *, job, resume_profile, job_store):
            raise CompatibilityProviderResponseError("OpenRouter response did not contain generated skills.")

    monkeypatch.setattr("app.api.routes.resume_profiles.get_summary_generation_service", lambda: FakeService())

    with pytest.raises(HTTPException) as error:
        generate_resume_skills(
            resume_profile_id=profile.id,
            payload=GenerateResumeSkillsRequest(job_id=job_id, resume_profile_id=profile.id),
            job_store=temp_job_store,
        )

    assert error.value.status_code == 502
    assert error.value.detail == "OpenRouter response did not contain generated skills."


def test_summary_prompt_falls_back_to_global_prompt_when_profile_prompt_is_empty(
    temp_job_store: SQLiteJobStore,
) -> None:
    job_id = _save_job(temp_job_store)
    job = temp_job_store.get_job_detail(job_id)
    assert job is not None
    profile = create_resume_profile(
        CreateResumeProfileRequest(name="Backend Resume"),
        job_store=temp_job_store,
    )
    temp_job_store.update_prompt_settings(
        UpdatePromptSettingsRequest(
            summary_prompt="Global summary prompt override",
            skills_prompt="Global skills prompt override",
        )
    )
    resume_profile = temp_job_store.get_resume_profile_detail(profile.id)
    assert resume_profile is not None

    service = OpenRouterSummaryGenerationService(
        provider=OpenRouterCompatibilityProvider(
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=1,
            auth_token="saved-local-key-9999",
            model="qwen/qwen3.6-plus:free",
            provider_name="openrouter",
        ),
    )

    summary_payload = service._build_message_payload(job=job, resume_profile=resume_profile, job_store=temp_job_store)
    skills_payload = service._build_skills_message_payload(job=job, resume_profile=resume_profile, job_store=temp_job_store)

    assert summary_payload["system"] == "Global summary prompt override"
    assert skills_payload["system"] == "Global skills prompt override"
