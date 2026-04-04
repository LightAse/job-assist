from pathlib import Path

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import CreateMasterLanguageRequest, CreateMasterSkillRequest, UpdateOpenRouterSettingsRequest
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


def test_save_candidate_compatibility_check_persists_result(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_candidate_compatibility_persistence.db")
    context = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/1234567890/",
        title="Senior Backend Engineer",
        company="Example Co",
        location="Remote",
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
    compatibility_check = store.save_candidate_compatibility_check(
        job_id=record.job_id,
        snapshot_id=record.snapshot_id,
        score=81,
        short_reason="Strong backend overlap with a few gaps.",
        strengths=["Python", "FastAPI"],
        gaps=["AWS"],
        raw_model_response='{"score":81}',
    )

    with store._connect() as connection:
        candidate_row = connection.execute(
            "SELECT * FROM candidate_compatibility_checks WHERE id = ?",
            (compatibility_check.id,),
        ).fetchone()

    assert candidate_row is not None
    assert candidate_row["job_id"] == record.job_id
    assert candidate_row["snapshot_id"] == record.snapshot_id
    assert candidate_row["score"] == 81
    assert candidate_row["short_reason"] == "Strong backend overlap with a few gaps."


def test_candidate_compatibility_latest_result_survives_store_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "test_candidate_compatibility_reopen.db"
    store = SQLiteJobStore(database_path)
    context = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/9876543210/",
        title="Platform Engineer",
        company="Example Co",
        location="Remote",
        visible_text="Platform Engineer at Example Co",
    )
    scrape_result = ScrapeCurrentResponse(
        plugin_name="linkedin_job_scraper",
        matched=True,
        source_url=context.url,
        raw_content=None,
        structured_data={
            "source": "linkedin",
            "external_job_id": "9876543210",
            "page_title": "Platform Engineer",
            "tentative_job_title": "Platform Engineer",
        },
    )

    record = store.save_matched_scrape(context, scrape_result)
    store.save_candidate_compatibility_check(
        job_id=record.job_id,
        snapshot_id=record.snapshot_id,
        score=45,
        short_reason="Relevant backend overlap, but several platform gaps remain.",
        strengths=["Python"],
        gaps=["Kubernetes", "Terraform"],
        raw_model_response='{"score":45}',
    )
    store.save_candidate_compatibility_check(
        job_id=record.job_id,
        snapshot_id=record.snapshot_id,
        score=67,
        short_reason="Improved fit after updating candidate data.",
        strengths=["Python", "CI/CD"],
        gaps=["Terraform"],
        raw_model_response='{"score":67}',
    )

    reopened_store = SQLiteJobStore(database_path)
    jobs = reopened_store.list_jobs()
    job_detail = reopened_store.get_job_detail(record.job_id)

    assert len(jobs) == 1
    assert jobs[0].latest_candidate_compatibility_check is not None
    assert jobs[0].latest_candidate_compatibility_check.score == 67
    assert jobs[0].latest_candidate_compatibility_check.short_reason == "Improved fit after updating candidate data."

    assert job_detail is not None
    assert job_detail.latest_candidate_compatibility_check is not None
    assert job_detail.latest_candidate_compatibility_check.score == 67
    assert job_detail.latest_candidate_compatibility_check.short_reason == "Improved fit after updating candidate data."


def test_job_status_survives_store_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "test_job_status_reopen.db"
    store = SQLiteJobStore(database_path)
    context = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/5555555555/",
        title="Staff Backend Engineer",
        company="Example Co",
        visible_text="Staff Backend Engineer at Example Co",
    )
    scrape_result = ScrapeCurrentResponse(
        plugin_name="linkedin_job_scraper",
        matched=True,
        source_url=context.url,
        raw_content=None,
        structured_data={
            "source": "linkedin",
            "external_job_id": "5555555555",
            "page_title": "Staff Backend Engineer",
            "tentative_job_title": "Staff Backend Engineer",
        },
    )

    record = store.save_matched_scrape(context, scrape_result)
    store.update_job_status(record.job_id, "applied")

    reopened_store = SQLiteJobStore(database_path)
    jobs = reopened_store.list_jobs()
    job_detail = reopened_store.get_job_detail(record.job_id)

    assert jobs[0].status == "applied"
    assert job_detail is not None
    assert job_detail.status == "applied"


def test_job_check_batch_persists_and_reloads_progress(tmp_path: Path) -> None:
    database_path = tmp_path / "test_job_check_batch_reopen.db"
    store = SQLiteJobStore(database_path)
    first_job_id = store.save_matched_scrape(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/1010101010/",
            title="Backend Engineer",
            company="Example Co",
            visible_text="Backend Engineer at Example Co",
        ),
        ScrapeCurrentResponse(
            plugin_name="linkedin_job_scraper",
            matched=True,
            source_url="https://www.linkedin.com/jobs/view/1010101010/",
            raw_content=None,
            structured_data={
                "source": "linkedin",
                "external_job_id": "1010101010",
                "page_title": "Backend Engineer",
                "tentative_job_title": "Backend Engineer",
            },
        ),
    ).job_id
    second_job_id = store.save_matched_scrape(
        ScrapeCurrentRequest(
            url="https://www.linkedin.com/jobs/view/2020202020/",
            title="Platform Engineer",
            company="Example Co",
            visible_text="Platform Engineer at Example Co",
        ),
        ScrapeCurrentResponse(
            plugin_name="linkedin_job_scraper",
            matched=True,
            source_url="https://www.linkedin.com/jobs/view/2020202020/",
            raw_content=None,
            structured_data={
                "source": "linkedin",
                "external_job_id": "2020202020",
                "page_title": "Platform Engineer",
                "tentative_job_title": "Platform Engineer",
            },
        ),
    ).job_id

    batch = store.create_job_check_batch(mode="all", job_ids=[first_job_id, second_job_id])
    store.update_job_check_batch_item(batch_id=batch.id, job_id=first_job_id, status_value="completed")
    store.update_job_check_batch_item(
        batch_id=batch.id,
        job_id=second_job_id,
        status_value="failed",
        error_message="Compatibility provider timed out.",
    )
    store.complete_job_check_batch(batch_id=batch.id, status_value="completed")

    reopened_store = SQLiteJobStore(database_path)
    reopened_batch = reopened_store.get_job_check_batch(batch.id)
    latest_batch = reopened_store.get_current_or_latest_job_check_batch()

    assert reopened_batch is not None
    assert reopened_batch.completed_jobs == 1
    assert reopened_batch.failed_jobs == 1
    assert [item.status for item in reopened_batch.items] == ["completed", "failed"]
    assert reopened_batch.items[1].error_message == "Compatibility provider timed out."
    assert latest_batch is not None
    assert latest_batch.id == batch.id


def test_save_matched_scrape_skips_duplicate_by_composite_key(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_duplicate_persistence.db")
    context = ScrapeCurrentRequest(
        url="https://jobs.example.com/openings/backend-engineer",
        title="Backend Engineer",
        company="Acme",
        visible_text="Backend Engineer at Acme",
    )
    scrape_result = ScrapeCurrentResponse(
        plugin_name="generic_job_capture",
        matched=True,
        source_url=context.url,
        raw_content=None,
        structured_data={
            "source": "generic",
            "page_title": "Backend Engineer",
            "tentative_job_title": "Backend Engineer",
        },
    )

    first = store.save_matched_scrape(context, scrape_result)
    second = store.save_matched_scrape(context, scrape_result)

    with store._connect() as connection:
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        snapshots_count = connection.execute("SELECT COUNT(*) FROM job_snapshots").fetchone()[0]

    assert first.status == "created"
    assert first.deduplicated is False
    assert second.status == "skipped"
    assert second.deduplicated is True
    assert second.reason == "duplicate"
    assert second.job_id == first.job_id
    assert second.snapshot_id is None
    assert jobs_count == 1
    assert snapshots_count == 1


def test_resume_profile_builder_persists_selected_master_data_and_preview(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_resume_builder.db")
    skill = store.create_master_skill(
        CreateMasterSkillRequest(
            name="Python",
            proficiency_level="Advanced",
            notes="Backend API development",
        )
    )
    language = store.create_master_language(
        CreateMasterLanguageRequest(
            name="English",
            proficiency="Professional working proficiency",
        )
    )

    profile = store.create_resume_profile(
        name="Backend Resume",
        headline="Backend Engineer",
        summary="English-first profile for international backend roles.",
        section_instructions={
            "summary": "Write a concise international summary.",
            "skills": "Keep only the strongest technical skills.",
        },
        selected_skill_ids=[skill.id],
        selected_language_ids=[language.id],
    )

    assert profile.selected_skill_ids == [skill.id]
    assert profile.selected_language_ids == [language.id]
    assert any(section.section_key == "summary" for section in profile.sections)
    assert any(section.section_key == "skills" for section in profile.sections)
    summary_section = next(section for section in profile.sections if section.section_key == "summary")
    skills_section = next(section for section in profile.sections if section.section_key == "skills")
    assert summary_section.custom_instructions == "Write a concise international summary."
    assert "Candidate guidance: English-first profile for international backend roles." in summary_section.source_material
    assert skills_section.custom_instructions == "Keep only the strongest technical skills."
    assert "Python (Advanced): Backend API development" in skills_section.source_material
    assert "Summary / About Me" in profile.content
    assert "Selected Skills" in profile.content
    assert "Python (Advanced): Backend API development" in profile.content
    assert "Languages" in profile.content
    assert "English (Professional working proficiency)" in profile.content

    workspace = store.get_resume_workspace()
    assert [item.id for item in workspace.resume_profiles] == [profile.id]
    assert [item.id for item in workspace.skills] == [skill.id]


def test_resume_profile_builder_rejects_more_than_twenty_skills(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_resume_skill_limit.db")
    skill_ids = [
        store.create_master_skill(CreateMasterSkillRequest(name=f"Skill {index}")).id
        for index in range(21)
    ]

    try:
        store.create_resume_profile(
            name="Too Many Skills",
            selected_skill_ids=skill_ids,
        )
    except ValueError as error:
        assert str(error) == "A resume profile can include at most 20 skills."
    else:
        raise AssertionError("Expected skill limit validation to raise a ValueError.")


def test_openrouter_settings_masks_saved_api_key(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_openrouter_settings.db")

    settings = store.update_openrouter_settings(
        UpdateOpenRouterSettingsRequest(
            api_key="abcd1234secret9876",
            provider="openrouter",
            default_model="openai/gpt-5-nano",
        )
    )

    assert settings.has_api_key is True
    assert settings.masked_api_key == "abcd**********9876"
    assert settings.api_key_source == "saved"
    assert settings.saved_provider == "openrouter"
    assert settings.effective_provider == "openrouter"
    assert settings.saved_default_model == "openai/gpt-5-nano"
    runtime_api_key, runtime_provider, runtime_model = store.get_openrouter_runtime_config()
    assert runtime_api_key == "abcd1234secret9876"
    assert runtime_provider == "openrouter"
    assert runtime_model == "openai/gpt-5-nano"


def test_openrouter_settings_fall_back_to_environment_when_no_saved_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-secret-1234")
    monkeypatch.setenv("OPENROUTER_MODEL", "minimax/minimax-m2.5:free")
    store = SQLiteJobStore(tmp_path / "test_openrouter_env_fallback.db")

    settings = store.get_openrouter_settings()

    assert settings.has_api_key is True
    assert settings.api_key_source == "environment"
    assert settings.masked_api_key == "env-*******1234"
    assert settings.effective_provider == "openrouter"
    assert settings.effective_default_model == "minimax/minimax-m2.5:free"


def test_openrouter_settings_reject_invalid_prefixed_model_id(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_openrouter_invalid_model.db")

    with pytest.raises(ValueError) as error:
        store.update_openrouter_settings(
            UpdateOpenRouterSettingsRequest(
                api_key="abcd1234secret9876",
                provider="openrouter",
                default_model="openrouter/qwen3.6-plus-free",
            )
        )

    assert "Invalid OpenRouter model id" in str(error.value)
