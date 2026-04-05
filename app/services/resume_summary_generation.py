import json
from dataclasses import dataclass

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import JobDetail, ResumeProfileDetail
from app.services.compatibility_errors import (
    CompatibilityProviderRequestError,
    CompatibilityProviderResponseError,
    CompatibilityProviderTimeoutError,
)
from app.services.compatibility_openrouter import OpenRouterCompatibilityProvider


DEFAULT_SUMMARY_SECTION_PROMPT = """You are generating a professional resume summary tailored to a specific job.

Use ONLY the candidate's provided source material. Do not invent experience, skills, or achievements.

Goals:

Align the summary with the job requirements
Highlight relevant skills and experience
Keep a professional and concise tone

Constraints:

Maximum 80–100 words
Output must be in English
Avoid generic phrases like "hardworking" or "team player"
Focus on concrete technical strengths and relevant experience

Input will include:

Job description
Candidate summary source
Selected skills/projects/experience

Output:

A single paragraph summary"""


DEFAULT_SKILLS_SECTION_PROMPT = """You are generating a resume skills section tailored to a specific job.

Use ONLY the candidate's provided source material. Do not invent skills, tools, certifications, or experience.

Goals:

Align the listed skills with the job requirements
Prioritize the most relevant candidate skills
Keep wording concise and resume-ready

Constraints:

Output must be in English
Return 6 to 12 items
Each item must be a short skill phrase, not a sentence
Do not include bullets, numbering, headings, or commentary
Do not include any skill that is not present in the source material

Output:

One skill per line"""


@dataclass(frozen=True)
class SummaryGenerationResult:
    generated_summary: str


@dataclass(frozen=True)
class SkillsGenerationResult:
    generated_skills: list[str]


@dataclass(frozen=True)
class OpenRouterSummaryGenerationService:
    provider: OpenRouterCompatibilityProvider

    def generate_summary(
        self,
        *,
        job: JobDetail,
        resume_profile: ResumeProfileDetail,
        job_store: SQLiteJobStore,
    ) -> SummaryGenerationResult:
        summary_section = next(
            (section for section in resume_profile.sections if section.section_key == "summary"),
            None,
        )
        skills_section = next(
            (section for section in resume_profile.sections if section.section_key == "skills"),
            None,
        )
        experience_section = next(
            (section for section in resume_profile.sections if section.section_key == "experience"),
            None,
        )
        projects_section = next(
            (section for section in resume_profile.sections if section.section_key == "projects"),
            None,
        )
        summary = self.generate_summary_from_sources(
            job=job,
            summary_source=summary_section.source_material if summary_section else "N/A",
            skills_source=skills_section.source_material if skills_section else "N/A",
            projects_source=projects_section.source_material if projects_section else "N/A",
            experience_source=experience_section.source_material if experience_section else "N/A",
            profile_prompt=summary_section.custom_instructions if summary_section else None,
            job_store=job_store,
        )
        job_store.save_resume_profile_section_generation(
            resume_profile_id=resume_profile.id,
            section_key="summary",
            generated_content=summary,
        )
        return SummaryGenerationResult(generated_summary=summary)

    def generate_skills(
        self,
        *,
        job: JobDetail,
        resume_profile: ResumeProfileDetail,
        job_store: SQLiteJobStore,
    ) -> SkillsGenerationResult:
        summary_section = next(
            (section for section in resume_profile.sections if section.section_key == "summary"),
            None,
        )
        skills_section = next(
            (section for section in resume_profile.sections if section.section_key == "skills"),
            None,
        )
        experience_section = next(
            (section for section in resume_profile.sections if section.section_key == "experience"),
            None,
        )
        projects_section = next(
            (section for section in resume_profile.sections if section.section_key == "projects"),
            None,
        )
        skills = self.generate_skills_from_sources(
            job=job,
            summary_source=summary_section.source_material if summary_section else "N/A",
            skills_source=skills_section.source_material if skills_section else "N/A",
            projects_source=projects_section.source_material if projects_section else "N/A",
            experience_source=experience_section.source_material if experience_section else "N/A",
            profile_prompt=skills_section.custom_instructions if skills_section else None,
            job_store=job_store,
        )
        job_store.save_resume_profile_section_generation(
            resume_profile_id=resume_profile.id,
            section_key="skills",
            generated_content="\n".join(f"- {skill}" for skill in skills),
        )
        return SkillsGenerationResult(generated_skills=skills)

    def generate_summary_from_sources(
        self,
        *,
        job: JobDetail,
        summary_source: str,
        skills_source: str,
        projects_source: str,
        experience_source: str,
        profile_prompt: str | None,
        job_store: SQLiteJobStore,
    ) -> str:
        session_id = self.provider._create_session()
        payload = self._build_message_payload_from_sources(
            job=job,
            summary_source=summary_source,
            skills_source=skills_source,
            projects_source=projects_source,
            experience_source=experience_source,
            profile_prompt=profile_prompt,
            job_store=job_store,
        )
        response_body = self.provider._post_json(f"/session/{session_id}/message", payload)
        return self._extract_summary_text(response_body)

    def generate_skills_from_sources(
        self,
        *,
        job: JobDetail,
        summary_source: str,
        skills_source: str,
        projects_source: str,
        experience_source: str,
        profile_prompt: str | None,
        job_store: SQLiteJobStore,
    ) -> list[str]:
        session_id = self.provider._create_session()
        payload = self._build_skills_message_payload_from_sources(
            job=job,
            summary_source=summary_source,
            skills_source=skills_source,
            projects_source=projects_source,
            experience_source=experience_source,
            profile_prompt=profile_prompt,
            job_store=job_store,
        )
        response_body = self.provider._post_json(f"/session/{session_id}/message", payload)
        return self._extract_skills_text(response_body)

    def _build_message_payload(
        self,
        *,
        job: JobDetail,
        resume_profile: ResumeProfileDetail,
        job_store: SQLiteJobStore,
    ) -> dict[str, object]:
        summary_section = next(
            (section for section in resume_profile.sections if section.section_key == "summary"),
            None,
        )
        skills_section = next(
            (section for section in resume_profile.sections if section.section_key == "skills"),
            None,
        )
        experience_section = next(
            (section for section in resume_profile.sections if section.section_key == "experience"),
            None,
        )
        projects_section = next(
            (section for section in resume_profile.sections if section.section_key == "projects"),
            None,
        )
        return self._build_message_payload_from_sources(
            job=job,
            summary_source=summary_section.source_material if summary_section else "N/A",
            skills_source=skills_section.source_material if skills_section else "N/A",
            projects_source=projects_section.source_material if projects_section else "N/A",
            experience_source=experience_section.source_material if experience_section else "N/A",
            profile_prompt=summary_section.custom_instructions if summary_section else None,
            job_store=job_store,
        )

    def _build_skills_message_payload(
        self,
        *,
        job: JobDetail,
        resume_profile: ResumeProfileDetail,
        job_store: SQLiteJobStore,
    ) -> dict[str, object]:
        summary_section = next(
            (section for section in resume_profile.sections if section.section_key == "summary"),
            None,
        )
        skills_section = next(
            (section for section in resume_profile.sections if section.section_key == "skills"),
            None,
        )
        experience_section = next(
            (section for section in resume_profile.sections if section.section_key == "experience"),
            None,
        )
        projects_section = next(
            (section for section in resume_profile.sections if section.section_key == "projects"),
            None,
        )
        return self._build_skills_message_payload_from_sources(
            job=job,
            summary_source=summary_section.source_material if summary_section else "N/A",
            skills_source=skills_section.source_material if skills_section else "N/A",
            projects_source=projects_section.source_material if projects_section else "N/A",
            experience_source=experience_section.source_material if experience_section else "N/A",
            profile_prompt=skills_section.custom_instructions if skills_section else None,
            job_store=job_store,
        )

    def _build_message_payload_from_sources(
        self,
        *,
        job: JobDetail,
        summary_source: str,
        skills_source: str,
        projects_source: str,
        experience_source: str,
        profile_prompt: str | None,
        job_store: SQLiteJobStore,
    ) -> dict[str, object]:
        job_description = self.provider._job_source_text(job.latest_snapshot) if job.latest_snapshot else "N/A"
        system_prompt = self._resolve_section_prompt(
            section_key="summary",
            profile_prompt=profile_prompt,
            job_store=job_store,
        )
        prompt = (
            f"Job description:\n{job_description}\n\n"
            f"Candidate summary source:\n{summary_source}\n\n"
            f"Selected skills:\n{skills_source}\n\n"
            f"Selected projects:\n{projects_source}\n\n"
            f"Selected experience:\n{experience_source}"
        )
        payload: dict[str, object] = {
            "parts": [{"type": "text", "text": prompt}],
            "system": system_prompt,
        }
        if self.provider.model:
            payload["model"] = self.provider.model
        return payload

    def _build_skills_message_payload_from_sources(
        self,
        *,
        job: JobDetail,
        summary_source: str,
        skills_source: str,
        projects_source: str,
        experience_source: str,
        profile_prompt: str | None,
        job_store: SQLiteJobStore,
    ) -> dict[str, object]:
        job_description = self.provider._job_source_text(job.latest_snapshot) if job.latest_snapshot else "N/A"
        system_prompt = self._resolve_section_prompt(
            section_key="skills",
            profile_prompt=profile_prompt,
            job_store=job_store,
        )
        prompt = (
            f"Job description:\n{job_description}\n\n"
            f"Candidate positioning:\n{summary_source}\n\n"
            f"Selected skills:\n{skills_source}\n\n"
            f"Selected projects:\n{projects_source}\n\n"
            f"Selected experience:\n{experience_source}"
        )
        payload: dict[str, object] = {
            "parts": [{"type": "text", "text": prompt}],
            "system": system_prompt,
        }
        if self.provider.model:
            payload["model"] = self.provider.model
        return payload

    @staticmethod
    def _extract_summary_text(response_body: dict[str, object]) -> str:
        candidates: list[object] = [
            response_body.get("text"),
            response_body.get("output"),
            response_body.get("content"),
        ]
        for part in response_body.get("parts", []):
            if isinstance(part, dict):
                candidates.extend([part.get("text"), part.get("output"), part.get("content")])
        info = response_body.get("info")
        if isinstance(info, dict):
            for part in info.get("parts", []):
                if isinstance(part, dict):
                    candidates.extend([part.get("text"), part.get("output"), part.get("content")])

        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, dict):
                text = candidate.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()

        raise CompatibilityProviderResponseError("OpenRouter response did not contain a generated summary.")

    @classmethod
    def _extract_skills_text(cls, response_body: dict[str, object]) -> list[str]:
        text = cls._extract_summary_text(response_body)
        skills = [
            item
            for item in (
                line.strip().lstrip("-*").strip()
                for line in text.splitlines()
            )
            if item
        ]
        if not skills:
            raise CompatibilityProviderResponseError("OpenRouter response did not contain generated skills.")
        return skills

    @staticmethod
    def _resolve_section_prompt(
        *,
        section_key: str,
        profile_prompt: str | None,
        job_store: SQLiteJobStore,
    ) -> str:
        normalized_profile_prompt = (profile_prompt or "").strip()
        if normalized_profile_prompt:
            return normalized_profile_prompt

        prompt_settings = job_store.get_prompt_settings()
        global_prompt = {
            "summary": prompt_settings.summary_prompt,
            "skills": prompt_settings.skills_prompt,
        }.get(section_key)
        normalized_global_prompt = (global_prompt or "").strip()
        if normalized_global_prompt:
            return normalized_global_prompt

        return {
            "summary": DEFAULT_SUMMARY_SECTION_PROMPT,
            "skills": DEFAULT_SKILLS_SECTION_PROMPT,
        }[section_key]


def get_summary_generation_service() -> OpenRouterSummaryGenerationService:
    return OpenRouterSummaryGenerationService(provider=OpenRouterCompatibilityProvider())
