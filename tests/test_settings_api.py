from pathlib import Path

from app.api.routes.settings import (
    get_openrouter_settings,
    get_prompt_settings,
    get_settings_models,
    refresh_settings_models,
    update_openrouter_settings,
    update_prompt_settings,
)
from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import UpdateOpenRouterSettingsRequest, UpdatePromptSettingsRequest


def test_settings_api_returns_masked_values(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_settings_api.db")

    updated = update_openrouter_settings(
        UpdateOpenRouterSettingsRequest(
            api_key="sk-local-secret-5678",
            provider="openrouter",
            default_model="openai/gpt-5-nano",
        ),
        job_store=store,
    )
    fetched = get_openrouter_settings(job_store=store)

    assert updated.masked_api_key == "sk-l************5678"
    assert fetched.masked_api_key == "sk-l************5678"
    assert fetched.saved_provider == "openrouter"
    assert fetched.saved_default_model == "openai/gpt-5-nano"


def test_settings_models_api_returns_dynamic_registry(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_settings_models_api.db")

    refresh = refresh_settings_models(job_store=store)
    fetched = get_settings_models(provider="openrouter", job_store=store)

    assert "openrouter" in refresh.providers
    assert fetched.providers == refresh.providers
    assert fetched.models
    assert all(model.provider == "openrouter" for model in fetched.models)
    assert any(model.model_id == "qwen/qwen3.6-plus:free" for model in fetched.models)


def test_blank_api_key_update_keeps_existing_saved_key(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_settings_keep_key.db")

    update_openrouter_settings(
        UpdateOpenRouterSettingsRequest(
            api_key="sk-local-secret-5678",
            provider="openrouter",
            default_model="openai/gpt-5-nano",
        ),
        job_store=store,
    )

    updated = update_openrouter_settings(
        UpdateOpenRouterSettingsRequest(
            api_key="",
            provider="openrouter",
            default_model="qwen/qwen3.6-plus:free",
        ),
        job_store=store,
    )

    assert updated.masked_api_key == "sk-l************5678"
    assert updated.saved_default_model == "qwen/qwen3.6-plus:free"


def test_prompt_settings_save_all_supported_sections(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "test_prompt_settings.db")

    updated = update_prompt_settings(
        UpdatePromptSettingsRequest(
            summary_prompt="Custom summary prompt",
            skills_prompt="Custom skills prompt",
            experience_prompt="Custom experience prompt",
            projects_prompt="Custom projects prompt",
        ),
        job_store=store,
    )
    fetched = get_prompt_settings(job_store=store)

    assert updated.summary_prompt == "Custom summary prompt"
    assert updated.skills_prompt == "Custom skills prompt"
    assert updated.experience_prompt == "Custom experience prompt"
    assert updated.projects_prompt == "Custom projects prompt"
    assert fetched.summary_prompt == "Custom summary prompt"
    assert fetched.skills_prompt == "Custom skills prompt"
    assert fetched.experience_prompt == "Custom experience prompt"
    assert fetched.projects_prompt == "Custom projects prompt"
    assert fetched.updated_at is not None
