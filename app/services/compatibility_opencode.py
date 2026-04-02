import json
import os
from dataclasses import dataclass
from socket import timeout as SocketTimeout
from urllib import error, request

from pydantic import ValidationError

from app.schemas.jobs import LatestJobSnapshot, ResumeProfile
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderRequestError,
    CompatibilityProviderResponseError,
    CompatibilityProviderTimeoutError,
)
from app.services.compatibility_models import CompatibilityEvaluation, CompatibilityStructuredOutput


@dataclass(frozen=True)
class OpenCodeCompatibilityProvider:
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    auth_token: str | None = None

    _prompt_visible_text_limit = 12_000
    _prompt_html_limit = 4_000
    _resume_limit = 12_000

    def __post_init__(self) -> None:
        if self.base_url is None:
            object.__setattr__(self, "base_url", os.environ.get("OPENCODE_BASE_URL", "http://127.0.0.1:4096"))
        if self.model is None:
            object.__setattr__(self, "model", os.environ.get("OPENCODE_MODEL"))
        if self.timeout_seconds is None:
            configured_timeout = os.environ.get("OPENCODE_TIMEOUT_SECONDS", "20")
            object.__setattr__(self, "timeout_seconds", float(configured_timeout))
        if self.auth_token is None:
            object.__setattr__(self, "auth_token", os.environ.get("OPENCODE_AUTH_TOKEN"))

    def evaluate(self, *, resume_profile: ResumeProfile, snapshot: LatestJobSnapshot) -> CompatibilityEvaluation:
        session_id = self._create_session()
        payload = self._build_message_payload(resume_profile=resume_profile, snapshot=snapshot)
        response_body = self._post_json(f"/session/{session_id}/message", payload)
        raw_model_response = json.dumps(response_body, indent=2, sort_keys=True)
        structured_output = self._extract_structured_output(response_body)
        return CompatibilityEvaluation(
            score=structured_output.score,
            decision=structured_output.decision,
            summary=structured_output.summary,
            strengths=structured_output.strengths,
            gaps=structured_output.gaps,
            raw_model_response=raw_model_response,
        )

    def _create_session(self) -> str:
        response_body = self._post_json("/session", {})
        session_id = response_body.get("id")
        if not session_id:
            raise CompatibilityProviderResponseError("OpenCode did not return a session id.")
        return str(session_id)

    def _build_message_payload(
        self,
        *,
        resume_profile: ResumeProfile,
        snapshot: LatestJobSnapshot,
    ) -> dict[str, object]:
        job_source_text = self._job_source_text(snapshot)
        resume_text = self._truncate_text(resume_profile.content, self._resume_limit)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "decision": {"type": "string"},
                "summary": {"type": "string"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "gaps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["score", "decision", "summary", "strengths", "gaps"],
        }
        prompt = (
            "Evaluate how well the resume profile matches the job snapshot. "
            "Return only structured output using the provided schema. "
            "Use the evidence in the supplied text. Do not invent facts.\n\n"
            f"Resume profile name: {resume_profile.name}\n"
            f"Resume profile content:\n{resume_text}\n\n"
            f"Job snapshot:\n{job_source_text}"
        )
        payload: dict[str, object] = {
            "parts": [{"type": "text", "text": prompt}],
            "system": (
                "You are evaluating resume compatibility for a job assistant backend. "
                "Return a concise structured evaluation."
            ),
            "format": {
                "type": "json_schema",
                "name": "compatibility_evaluation",
                "schema": schema,
            },
        }
        if self.model:
            payload["model"] = self.model
        return payload

    def _job_source_text(self, snapshot: LatestJobSnapshot) -> str:
        preferred_text = snapshot.visible_text or ""
        if preferred_text.strip():
            body_text = self._truncate_text(preferred_text, self._prompt_visible_text_limit)
            source_label = "visible_text"
        else:
            body_text = self._truncate_text(snapshot.html or "", self._prompt_html_limit)
            source_label = "html"

        return (
            f"title: {snapshot.title or 'N/A'}\n"
            f"company: {snapshot.company or 'N/A'}\n"
            f"location: {snapshot.location or 'N/A'}\n"
            f"source_field: {source_label}\n"
            f"source_text:\n{body_text or 'N/A'}"
        )

    @staticmethod
    def _truncate_text(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + "\n...[truncated]"

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        if not self.base_url:
            raise CompatibilityProviderConfigurationError("OPENCODE_BASE_URL is not configured.")

        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise CompatibilityProviderRequestError(
                f"OpenCode request failed with status {exc.code}: {detail or exc.reason}"
            ) from exc
        except error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, SocketTimeout):
                raise CompatibilityProviderTimeoutError("OpenCode request timed out.") from exc
            raise CompatibilityProviderRequestError(f"OpenCode request failed: {reason}") from exc
        except TimeoutError as exc:
            raise CompatibilityProviderTimeoutError("OpenCode request timed out.") from exc

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise CompatibilityProviderResponseError("OpenCode returned non-JSON response data.") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    @classmethod
    def _extract_structured_output(cls, response_body: dict[str, object]) -> CompatibilityStructuredOutput:
        candidates = [
            response_body.get("structured_output"),
            response_body.get("output"),
            cls._nested_get(response_body, "info", "structured_output"),
            cls._nested_get(response_body, "info", "output"),
        ]
        candidates.extend(cls._extract_part_candidates(response_body))

        for candidate in candidates:
            if candidate is None:
                continue
            parsed = cls._coerce_candidate(candidate)
            if parsed is None:
                continue
            try:
                return CompatibilityStructuredOutput.model_validate(parsed)
            except ValidationError:
                continue

        raise CompatibilityProviderResponseError("OpenCode response did not contain valid structured compatibility output.")

    @staticmethod
    def _nested_get(payload: dict[str, object], *keys: str) -> object:
        current: object = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @classmethod
    def _extract_part_candidates(cls, response_body: dict[str, object]) -> list[object]:
        candidates: list[object] = []
        for part in response_body.get("parts", []):
            if isinstance(part, dict):
                candidates.append(part.get("structured_output"))
                candidates.append(part.get("output"))
                candidates.append(part.get("json"))
                candidates.append(part.get("text"))
        info = response_body.get("info")
        if isinstance(info, dict):
            for part in info.get("parts", []):
                if isinstance(part, dict):
                    candidates.append(part.get("structured_output"))
                    candidates.append(part.get("output"))
                    candidates.append(part.get("json"))
                    candidates.append(part.get("text"))
        return candidates

    @staticmethod
    def _coerce_candidate(candidate: object) -> dict[str, object] | None:
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                return parsed
        return None
