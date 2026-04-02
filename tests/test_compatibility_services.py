from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.jobs import run_compatibility_check
from app.api.routes.resume_profiles import create_resume_profile
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import CreateResumeProfileRequest, LatestJobSnapshot, ResumeProfile, RunCompatibilityCheckRequest
from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse
from app.services.compatibility import CompatibilityService, get_compatibility_service
from app.services.compatibility_deterministic import DeterministicCompatibilityProvider
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderRequestError,
    CompatibilityProviderTimeoutError,
)
from app.services.compatibility_opencode import OpenCodeCompatibilityProvider


def _snapshot() -> LatestJobSnapshot:
    return LatestJobSnapshot(
        id=1,
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Senior Backend Engineer at Example Co\nPython FastAPI Postgres Remote",
        html="<html>Senior Backend Engineer</html>",
        plugin_name="linkedin_job_scraper",
        captured_at="2026-04-02T00:00:00+00:00",
    )


def _resume_profile() -> ResumeProfile:
    return ResumeProfile(
        id=7,
        name="Backend Resume",
        content="Senior backend engineer with Python FastAPI Postgres experience in remote teams.",
        created_at="2026-04-02T00:00:00+00:00",
    )


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


def test_deterministic_provider_still_returns_expected_shape() -> None:
    evaluation = DeterministicCompatibilityProvider().evaluate(
        resume_profile=_resume_profile(),
        snapshot=_snapshot(),
    )

    assert 0 <= evaluation.score <= 100
    assert evaluation.decision in {"strong_match", "borderline", "weak_match"}
    assert evaluation.summary
    assert evaluation.strengths
    assert evaluation.gaps
    assert '"method": "keyword_overlap_v1"' in evaluation.raw_model_response


def test_provider_selection_defaults_to_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPATIBILITY_PROVIDER", raising=False)

    service = get_compatibility_service()

    assert isinstance(service.provider, DeterministicCompatibilityProvider)


def test_provider_selection_supports_opencode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPATIBILITY_PROVIDER", "opencode")

    service = get_compatibility_service()

    assert isinstance(service.provider, OpenCodeCompatibilityProvider)


def test_provider_selection_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPATIBILITY_PROVIDER", "unknown")

    with pytest.raises(CompatibilityProviderConfigurationError):
        get_compatibility_service()


def test_opencode_response_is_normalized_from_text_json(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenCodeCompatibilityProvider(base_url="http://opencode.test", timeout_seconds=1)
    responses = iter(
        [
            {"id": "session-123"},
            {
                "parts": [
                    {
                        "text": (
                            '{"score": 82, "decision": "strong_match", "summary": "Strong overlap.", '
                            '"strengths": ["Python", "FastAPI"], "gaps": ["AWS"]}'
                        )
                    }
                ]
            },
        ]
    )

    monkeypatch.setattr(
        OpenCodeCompatibilityProvider,
        "_post_json",
        lambda self, path, payload: next(responses),
    )

    evaluation = provider.evaluate(
        resume_profile=_resume_profile(),
        snapshot=_snapshot(),
    )

    assert evaluation.score == 82
    assert evaluation.decision == "strong_match"
    assert evaluation.summary == "Strong overlap."
    assert evaluation.strengths == ["Python", "FastAPI"]
    assert evaluation.gaps == ["AWS"]
    assert '"parts"' in evaluation.raw_model_response
    assert '\\"score\\": 82' in evaluation.raw_model_response


def test_opencode_provider_prefers_visible_text_and_truncates_payload() -> None:
    provider = OpenCodeCompatibilityProvider(base_url="http://opencode.test", timeout_seconds=1)
    snapshot = LatestJobSnapshot(
        id=1,
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
        visible_text="A" * 12_500,
        html="B" * 5_000,
        plugin_name="linkedin_job_scraper",
        captured_at="2026-04-02T00:00:00+00:00",
    )

    payload = provider._build_message_payload(resume_profile=_resume_profile(), snapshot=snapshot)
    prompt = payload["parts"][0]["text"]

    assert "source_field: visible_text" in prompt
    assert "BBBB" not in prompt
    assert "...[truncated]" in prompt


def test_provider_failure_maps_to_clear_api_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "provider_failure.db")
    job_id = _save_job(store)
    resume_profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="Backend Resume",
            content="Python FastAPI Postgres experience.",
        ),
        job_store=store,
    )

    class FailingService:
        def evaluate(self, *, resume_profile: ResumeProfile, snapshot: LatestJobSnapshot):
            raise CompatibilityProviderTimeoutError("timed out")

    monkeypatch.setattr("app.api.routes.jobs.get_compatibility_service", lambda: FailingService())

    with pytest.raises(HTTPException) as error:
        run_compatibility_check(
            job_id=job_id,
            payload=RunCompatibilityCheckRequest(resume_profile_id=resume_profile.id),
            job_store=store,
        )

    assert error.value.status_code == 504
    assert error.value.detail == "Compatibility provider timed out."

    with store._connect() as connection:
        checks_count = connection.execute("SELECT COUNT(*) FROM compatibility_checks").fetchone()[0]

    assert checks_count == 0


def test_provider_request_failure_maps_to_bad_gateway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "provider_request_failure.db")
    job_id = _save_job(store)
    resume_profile = create_resume_profile(
        CreateResumeProfileRequest(
            name="Backend Resume",
            content="Python FastAPI Postgres experience.",
        ),
        job_store=store,
    )

    class FailingService:
        def evaluate(self, *, resume_profile: ResumeProfile, snapshot: LatestJobSnapshot):
            raise CompatibilityProviderRequestError("OpenCode request failed: connection refused")

    monkeypatch.setattr("app.api.routes.jobs.get_compatibility_service", lambda: FailingService())

    with pytest.raises(HTTPException) as error:
        run_compatibility_check(
            job_id=job_id,
            payload=RunCompatibilityCheckRequest(resume_profile_id=resume_profile.id),
            job_store=store,
        )

    assert error.value.status_code == 502
    assert "OpenCode request failed" in error.value.detail
