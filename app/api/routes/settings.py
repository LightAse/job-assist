from fastapi import APIRouter, Depends, HTTPException, status

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.schemas.jobs import (
    OpenRouterSettings,
    PromptSettings,
    SettingsModelsResponse,
    UpdateOpenRouterSettingsRequest,
    UpdatePromptSettingsRequest,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/openrouter", response_model=OpenRouterSettings)
def get_openrouter_settings(job_store: SQLiteJobStore = Depends(get_job_store)) -> OpenRouterSettings:
    return job_store.get_openrouter_settings()


@router.put("/openrouter", response_model=OpenRouterSettings)
def update_openrouter_settings(
    payload: UpdateOpenRouterSettingsRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> OpenRouterSettings:
    try:
        return job_store.update_openrouter_settings(payload)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/models", response_model=SettingsModelsResponse)
def get_settings_models(
    provider: str | None = None,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> SettingsModelsResponse:
    providers, models, updated_at = job_store.list_settings_models(provider=provider)
    return SettingsModelsResponse(providers=providers, models=models, updated_at=updated_at)


@router.post("/models/refresh", response_model=SettingsModelsResponse)
def refresh_settings_models(job_store: SQLiteJobStore = Depends(get_job_store)) -> SettingsModelsResponse:
    providers, models, updated_at = job_store.refresh_openrouter_model_registry()
    return SettingsModelsResponse(providers=providers, models=models, updated_at=updated_at)


@router.get("/prompts", response_model=PromptSettings)
def get_prompt_settings(job_store: SQLiteJobStore = Depends(get_job_store)) -> PromptSettings:
    return job_store.get_prompt_settings()


@router.put("/prompts", response_model=PromptSettings)
def update_prompt_settings(
    payload: UpdatePromptSettingsRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> PromptSettings:
    return job_store.update_prompt_settings(payload)
