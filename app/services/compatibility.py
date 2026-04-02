import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.schemas.jobs import LatestJobSnapshot, ResumeProfile
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderResponseError,
)
from app.services.compatibility_models import CompatibilityEvaluation, CompatibilityStructuredOutput
from app.services.compatibility_deterministic import DeterministicCompatibilityProvider
from app.services.compatibility_opencode import OpenCodeCompatibilityProvider


class CompatibilityProvider(Protocol):
    def evaluate(self, *, resume_profile: ResumeProfile, snapshot: LatestJobSnapshot) -> CompatibilityEvaluation:
        ...


@dataclass(frozen=True)
class CompatibilityService:
    provider: CompatibilityProvider

    def evaluate(self, *, resume_profile: ResumeProfile, snapshot: LatestJobSnapshot) -> CompatibilityEvaluation:
        return self.provider.evaluate(resume_profile=resume_profile, snapshot=snapshot)


def get_compatibility_service() -> CompatibilityService:
    provider_name = os.environ.get("COMPATIBILITY_PROVIDER", "deterministic").strip().lower()
    if provider_name == "deterministic":
        return CompatibilityService(provider=DeterministicCompatibilityProvider())
    if provider_name == "opencode":
        return CompatibilityService(provider=OpenCodeCompatibilityProvider())
    raise CompatibilityProviderConfigurationError(
        f"Unsupported compatibility provider: {provider_name}."
    )


def validate_structured_output(data: object) -> CompatibilityStructuredOutput:
    try:
        return CompatibilityStructuredOutput.model_validate(data)
    except ValidationError as error:
        raise CompatibilityProviderResponseError("Compatibility provider returned invalid structured output.") from error
