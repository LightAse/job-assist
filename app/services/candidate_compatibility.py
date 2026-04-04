import json
from dataclasses import dataclass

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import JobDetail
from app.services.compatibility_errors import CompatibilityProviderResponseError
from app.services.compatibility_models import (
    CandidateCompatibilityEvaluation,
    CandidateCompatibilityStructuredOutput,
)
from app.services.compatibility_openrouter import OpenRouterCompatibilityProvider


DEFAULT_CANDIDATE_COMPATIBILITY_PROMPT = """You are evaluating a candidate's fit for a specific job.

Use ONLY the provided candidate data and the provided job data.
Do not invent qualifications, achievements, certifications, or experience.
Be conservative and score fit only when there is clear evidence in the candidate data.

Return JSON matching the required schema:
- score: integer from 0 to 100
- short_reason: one short sentence
- strengths: optional concise list
- gaps: optional concise list"""


@dataclass(frozen=True)
class CandidateCompatibilityService:
    provider: OpenRouterCompatibilityProvider

    def evaluate(self, *, job: JobDetail, job_store: SQLiteJobStore) -> CandidateCompatibilityEvaluation:
        session_id = self.provider._create_session()
        payload = self._build_message_payload(job=job, job_store=job_store)
        response_body = self.provider._post_json(f"/session/{session_id}/message", payload)
        raw_model_response = json.dumps(response_body, indent=2, sort_keys=True)
        structured_output = self._extract_structured_output(response_body)
        return CandidateCompatibilityEvaluation(
            score=structured_output.score,
            short_reason=structured_output.short_reason,
            strengths=structured_output.strengths,
            gaps=structured_output.gaps,
            raw_model_response=raw_model_response,
        )

    def _build_message_payload(self, *, job: JobDetail, job_store: SQLiteJobStore) -> dict[str, object]:
        job_description = self.provider._job_source_text(job.latest_snapshot) if job.latest_snapshot else "N/A"
        candidate_source = self._build_candidate_source(job_store)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "short_reason": {"type": "string"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "gaps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["score", "short_reason", "strengths", "gaps"],
        }
        prompt = (
            f"Candidate data:\n{candidate_source}\n\n"
            f"Job data:\n{job_description}"
        )
        payload: dict[str, object] = {
            "parts": [{"type": "text", "text": prompt}],
            "system": DEFAULT_CANDIDATE_COMPATIBILITY_PROMPT,
            "format": {
                "type": "json_schema",
                "name": "candidate_job_compatibility",
                "schema": schema,
            },
        }
        if self.provider.model:
            payload["model"] = self.provider.model
        return payload

    @staticmethod
    def _build_candidate_source(job_store: SQLiteJobStore) -> str:
        workspace = job_store.get_resume_workspace()
        lines: list[str] = []
        if workspace.candidate_profile.summary:
            lines.extend(["Candidate summary:", workspace.candidate_profile.summary, ""])
        if workspace.skills:
            lines.append("Skills:")
            lines.extend(
                f"- {item.name}{f' ({item.proficiency_level})' if item.proficiency_level else ''}{f': {item.notes}' if item.notes else ''}"
                for item in workspace.skills
            )
            lines.append("")
        if workspace.work_experiences:
            lines.append("Work experience:")
            for item in workspace.work_experiences:
                lines.append(f"- {item.title} | {item.company}")
                if item.summary:
                    lines.append(f"  Context: {item.summary}")
                lines.extend(f"  - {highlight}" for highlight in item.highlights)
            lines.append("")
        if workspace.projects:
            lines.append("Projects:")
            for item in workspace.projects:
                lines.append(f"- {item.name}")
                if item.role:
                    lines.append(f"  Role: {item.role}")
                if item.summary:
                    lines.append(f"  Summary: {item.summary}")
                if item.technologies:
                    lines.append(f"  Technologies: {', '.join(item.technologies)}")
            lines.append("")
        if workspace.education:
            lines.append("Education:")
            lines.extend(f"- {item.degree} | {item.institution}" for item in workspace.education)
            lines.append("")
        if workspace.certifications:
            lines.append("Certifications:")
            lines.extend(f"- {item.name} | {item.issuer}" for item in workspace.certifications)
            lines.append("")
        if workspace.languages:
            lines.append("Languages:")
            lines.extend(f"- {item.name} ({item.proficiency})" for item in workspace.languages)
            lines.append("")
        if workspace.links:
            lines.append("Links:")
            lines.extend(f"- {item.label}: {item.url}" for item in workspace.links)
        return "\n".join(lines).strip() or "No candidate data available."

    @staticmethod
    def _extract_structured_output(response_body: dict[str, object]) -> CandidateCompatibilityStructuredOutput:
        candidates: list[object] = [
            response_body.get("structured_output"),
            response_body.get("output"),
            response_body.get("text"),
        ]
        for part in response_body.get("parts", []):
            if isinstance(part, dict):
                candidates.extend([part.get("structured_output"), part.get("output"), part.get("json"), part.get("text")])

        for candidate in candidates:
            parsed: object = candidate
            if isinstance(candidate, str):
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
            if isinstance(parsed, dict):
                try:
                    return CandidateCompatibilityStructuredOutput.model_validate(parsed)
                except Exception:
                    continue

        raise CompatibilityProviderResponseError("OpenRouter response did not contain valid candidate compatibility output.")


def get_candidate_compatibility_service() -> CandidateCompatibilityService:
    return CandidateCompatibilityService(provider=OpenRouterCompatibilityProvider())
