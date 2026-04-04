import json
import logging
import os
from dataclasses import dataclass
from socket import timeout as SocketTimeout
from urllib import error, request
from urllib.parse import urlparse

from pydantic import ValidationError

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import LatestJobSnapshot, ResumeProfile
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderRequestError,
    CompatibilityProviderResponseError,
    CompatibilityProviderTimeoutError,
)
from app.services.compatibility_models import CompatibilityEvaluation, CompatibilityStructuredOutput


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenRouterCompatibilityProvider:
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    auth_token: str | None = None
    provider_name: str | None = None

    _prompt_visible_text_limit = 12_000
    _prompt_html_limit = 4_000
    _resume_limit = 12_000

    def __post_init__(self) -> None:
        runtime_api_key, runtime_provider, runtime_model = SQLiteJobStore().get_openrouter_runtime_config()
        if self.base_url is None:
            object.__setattr__(
                self,
                "base_url",
                os.environ.get("OPENROUTER_BASE_URL")
                or "https://openrouter.ai/api/v1",
            )
        if self.model is None:
            object.__setattr__(self, "model", runtime_model)
        if self.timeout_seconds is None:
            configured_timeout = os.environ.get("OPENROUTER_TIMEOUT_SECONDS") or os.environ.get("OPENCODE_TIMEOUT_SECONDS", "20")
            object.__setattr__(self, "timeout_seconds", float(configured_timeout))
        if self.auth_token is None:
            object.__setattr__(self, "auth_token", runtime_api_key)
        if self.provider_name is None:
            object.__setattr__(self, "provider_name", runtime_provider or "openrouter")

        self._validate_runtime_config()

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
        return "openrouter-chat"

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
        self._validate_runtime_config()

        if path == "/session":
            return {"id": "openrouter-chat"}

        if not path.startswith("/session/") or not path.endswith("/message"):
            raise CompatibilityProviderConfigurationError(f"Unsupported OpenRouter request path: {path}")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        request_payload = self._build_chat_completions_payload(payload)
        self._log_request_config(url=url, payload=request_payload)

        body = json.dumps(request_payload).encode("utf-8")
        http_request = request.Request(
            url,
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
                f"OpenRouter request failed for {url} with status {exc.code}: {detail or exc.reason}"
            ) from exc
        except error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, SocketTimeout):
                raise CompatibilityProviderTimeoutError("OpenRouter request timed out.") from exc
            raise CompatibilityProviderRequestError(f"OpenRouter request failed for {url}: {reason}") from exc
        except TimeoutError as exc:
            raise CompatibilityProviderTimeoutError("OpenRouter request timed out.") from exc

        try:
            parsed_response = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise CompatibilityProviderResponseError("OpenRouter returned non-JSON response data.") from exc

        return self._normalize_chat_response(parsed_response)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _validate_runtime_config(self) -> None:
        if (self.provider_name or "").strip().lower() not in {"", "openrouter"}:
            raise CompatibilityProviderConfigurationError(
                f"OpenRouter provider is misconfigured: expected provider 'openrouter', got '{self.provider_name}'."
            )
        if not self.base_url:
            raise CompatibilityProviderConfigurationError("OpenRouter base URL is not configured.")
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        if not parsed.scheme or not parsed.netloc:
            raise CompatibilityProviderConfigurationError(
                f"OpenRouter base URL is invalid: {self.base_url!r}."
            )
        if host in {"localhost", "127.0.0.1", "::1"}:
            raise CompatibilityProviderConfigurationError(
                "OpenRouter base URL points to a local host. Configure the real OpenRouter API endpoint instead."
            )
        if "/session" in parsed.path:
            raise CompatibilityProviderConfigurationError(
                "OpenRouter base URL is using a stale session-style endpoint. Configure the API base URL, for example https://openrouter.ai/api/v1."
            )
        if not self.auth_token:
            raise CompatibilityProviderConfigurationError("OpenRouter API key is not configured.")
        if not self.model:
            raise CompatibilityProviderConfigurationError("OpenRouter model is not configured.")
        if not self._is_valid_openrouter_model_id(self.model):
            raise CompatibilityProviderConfigurationError(
                f"OpenRouter model id is invalid: {self.model!r}. Use the real API model id, for example qwen/qwen3.6-plus:free."
            )

    def _build_chat_completions_payload(self, payload: dict[str, object]) -> dict[str, object]:
        message_text = self._extract_prompt_text(payload)
        request_payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": str(payload.get("system") or "You are a helpful assistant.")},
                {"role": "user", "content": message_text},
            ],
        }
        format_block = payload.get("format")
        if isinstance(format_block, dict) and format_block.get("type") == "json_schema":
            request_payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": format_block.get("name") or "response",
                    "strict": True,
                    "schema": format_block.get("schema") or {},
                },
            }
        return request_payload

    @staticmethod
    def _extract_prompt_text(payload: dict[str, object]) -> str:
        parts = payload.get("parts", [])
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip():
                    return part["text"]
        raise CompatibilityProviderConfigurationError("OpenRouter request payload did not include a text prompt.")

    @staticmethod
    def _is_valid_openrouter_model_id(model_id: str) -> bool:
        normalized = model_id.strip()
        if not normalized or " " in normalized:
            return False
        if normalized == "openrouter/auto":
            return True
        if normalized.startswith("openrouter/"):
            return False
        return "/" in normalized

    def _log_request_config(self, *, url: str, payload: dict[str, object]) -> None:
        logger.info(
            "OpenRouter request config: provider=%s model=%s base_url=%s url=%s api_key_present=%s",
            self.provider_name,
            self.model,
            self.base_url,
            url,
            bool(self.auth_token),
        )
        logger.debug("OpenRouter request payload keys: %s", sorted(payload.keys()))

    @staticmethod
    def _normalize_chat_response(response_body: dict[str, object]) -> dict[str, object]:
        text = OpenRouterCompatibilityProvider._extract_chat_text(response_body)
        return {
            "text": text,
            "output": text,
            "content": text,
            "parts": [{"text": text}],
            "raw_response": response_body,
        }

    @staticmethod
    def _extract_chat_text(response_body: dict[str, object]) -> str:
        choices = response_body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise CompatibilityProviderResponseError("OpenRouter response did not include choices.")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise CompatibilityProviderResponseError("OpenRouter response choice was malformed.")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise CompatibilityProviderResponseError("OpenRouter response did not include a message.")

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            normalized = "\n".join(part.strip() for part in parts if part.strip()).strip()
            if normalized:
                return normalized

        raise CompatibilityProviderResponseError("OpenRouter response did not contain text content.")

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

        raise CompatibilityProviderResponseError("OpenRouter response did not contain valid structured compatibility output.")

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


OpenCodeCompatibilityProvider = OpenRouterCompatibilityProvider
