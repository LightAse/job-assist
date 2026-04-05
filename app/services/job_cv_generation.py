import re
from dataclasses import dataclass

from app.persistence.sqlite import SQLiteJobStore
from app.schemas.jobs import (
    CandidateProfile,
    GeneratedCvArtifact,
    JobDetail,
    MasterCertification,
    MasterEducation,
    MasterLanguage,
    MasterProject,
    MasterWorkExperience,
    ResumeWorkspace,
)
from app.services.resume_summary_generation import get_summary_generation_service


@dataclass(frozen=True)
class SelectedCvContent:
    work_experiences: list[MasterWorkExperience]
    projects: list[MasterProject]


class JobCvGenerationService:
    def generate_cv(self, *, job: JobDetail, job_store: SQLiteJobStore) -> GeneratedCvArtifact:
        if job.latest_snapshot is None:
            raise ValueError("No job snapshot is available for CV generation.")

        workspace = job_store.get_resume_workspace()
        candidate_profile = workspace.candidate_profile
        self._validate_candidate_profile(candidate_profile)

        selected_content = self._select_relevant_content(job=job, workspace=workspace)
        summary_source = self._build_summary_source(
            candidate_profile=candidate_profile,
            selected_content=selected_content,
        )
        skills_source = self._build_skills_source(workspace=workspace)
        experience_source = self._build_experience_source(selected_content.work_experiences)
        projects_source = self._build_projects_source(selected_content.projects)

        generator = get_summary_generation_service()
        summary = generator.generate_summary_from_sources(
            job=job,
            summary_source=summary_source,
            skills_source=skills_source,
            projects_source=projects_source,
            experience_source=experience_source,
            profile_prompt=None,
            job_store=job_store,
        )
        skills = generator.generate_skills_from_sources(
            job=job,
            summary_source=summary_source,
            skills_source=skills_source,
            projects_source=projects_source,
            experience_source=experience_source,
            profile_prompt=None,
            job_store=job_store,
        )

        content = self._assemble_resume(
            candidate_profile=candidate_profile,
            summary=summary,
            skills=skills,
            work_experiences=selected_content.work_experiences,
            projects=selected_content.projects,
            education=workspace.education,
            certifications=workspace.certifications,
            languages=workspace.languages,
        )
        return job_store.save_generated_cv_artifact(
            job_id=job.id,
            company=job.latest_snapshot.company if job.latest_snapshot else None,
            job_title=job.latest_snapshot.title if job.latest_snapshot else None,
            summary=summary,
            skills=skills,
            content=content,
        )

    def _validate_candidate_profile(self, candidate_profile: CandidateProfile) -> None:
        missing_fields = []
        if not (candidate_profile.full_name or "").strip():
            missing_fields.append("full name")
        if not (candidate_profile.email or "").strip():
            missing_fields.append("email")
        if not (candidate_profile.phone or "").strip():
            missing_fields.append("phone")
        if not (candidate_profile.location or "").strip():
            missing_fields.append("location")
        if missing_fields:
            raise ValueError(f"Candidate Data is missing required fields: {', '.join(missing_fields)}.")

    def _select_relevant_content(self, *, job: JobDetail, workspace: ResumeWorkspace) -> SelectedCvContent:
        job_text = self._normalize_text(self._job_text(job))

        ranked_experiences = sorted(
            (
                (experience, self._experience_score(experience, job_text))
                for experience in workspace.work_experiences
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        ranked_projects = sorted(
            (
                (project, self._project_score(project, job_text))
                for project in workspace.projects
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        best_experience_score = ranked_experiences[0][1] if ranked_experiences else 0
        best_project_score = ranked_projects[0][1] if ranked_projects else 0
        relevant_experiences = [experience for experience, score in ranked_experiences if score > 0]
        relevant_projects = [project for project, score in ranked_projects if score > 0]
        experience_is_competitive = best_experience_score >= max(1, best_project_score - 1)
        project_is_competitive = best_project_score >= max(1, best_experience_score - 1)

        if best_experience_score == 0 and best_project_score == 0:
            selected_work_experiences = [experience for experience, _ in ranked_experiences[: min(2, len(ranked_experiences))]]
            selected_projects = [project for project, _ in ranked_projects[:1]]
        elif best_project_score > best_experience_score and not experience_is_competitive:
            selected_work_experiences = []
            selected_projects = relevant_projects[:2]
        elif best_experience_score > best_project_score and not project_is_competitive:
            selected_work_experiences = relevant_experiences[:3]
            selected_projects = []
        else:
            selected_work_experiences = relevant_experiences[:3]
            selected_projects = relevant_projects[:2]

        return SelectedCvContent(
            work_experiences=selected_work_experiences,
            projects=selected_projects,
        )

    def _assemble_resume(
        self,
        *,
        candidate_profile: CandidateProfile,
        summary: str,
        skills: list[str],
        work_experiences: list[MasterWorkExperience],
        projects: list[MasterProject],
        education: list[MasterEducation],
        certifications: list[MasterCertification],
        languages: list[MasterLanguage],
    ) -> str:
        sections = [self._render_header(candidate_profile), "## Professional Summary", summary.strip()]

        if skills:
            sections.extend(["## Skills", "\n".join(f"- {skill}" for skill in skills)])

        if work_experiences:
            sections.extend(["## Professional Experience", self._render_experience_section(work_experiences)])

        if projects:
            sections.extend(["## Projects", self._render_projects_section(projects)])

        if education:
            sections.extend(["## Education", self._render_education_section(education)])

        if certifications:
            sections.extend(["## Certifications", self._render_certifications_section(certifications)])

        if languages:
            sections.extend(["## Languages", self._render_languages_section(languages)])

        return "\n\n".join(section for section in sections if section and section.strip()).strip() + "\n"

    def _render_header(self, candidate_profile: CandidateProfile) -> str:
        contact_parts = [
            candidate_profile.email,
            candidate_profile.phone,
            candidate_profile.location,
            candidate_profile.linkedin_url,
            candidate_profile.github_url,
            candidate_profile.portfolio_url,
        ]
        return "\n".join(
            [
                candidate_profile.full_name.strip(),
                " | ".join(part.strip() for part in contact_parts if part and part.strip()),
            ]
        )

    def _render_experience_section(self, work_experiences: list[MasterWorkExperience]) -> str:
        entries: list[str] = []
        for experience in work_experiences:
            header = f"**{experience.title} | {experience.company}**"
            meta_parts = [
                part
                for part in [
                    experience.location,
                    self._format_date_range(experience.start_date, experience.end_date),
                ]
                if part
            ]
            body_parts = [header]
            if meta_parts:
                body_parts.append(" | ".join(meta_parts))
            if experience.summary:
                body_parts.append(experience.summary.strip())
            if experience.highlights:
                body_parts.extend(f"- {highlight.strip()}" for highlight in experience.highlights if highlight.strip())
            entries.append("\n".join(body_parts))
        return "\n\n".join(entries)

    def _render_projects_section(self, projects: list[MasterProject]) -> str:
        entries: list[str] = []
        for project in projects:
            header_parts = [project.name]
            if project.role:
                header_parts.append(project.role)
            header = f"**{' | '.join(header_parts)}**"
            body_parts = [header]
            if project.summary:
                body_parts.append(project.summary.strip())
            if project.technologies:
                body_parts.append(f"Technologies: {', '.join(project.technologies)}")
            if project.url:
                body_parts.append(project.url.strip())
            entries.append("\n".join(body_parts))
        return "\n\n".join(entries)

    def _render_education_section(self, education: list[MasterEducation]) -> str:
        entries = []
        for item in education:
            title = item.degree
            if item.field_of_study:
                title = f"{title}, {item.field_of_study}"
            lines = [f"**{title} | {item.institution}**"]
            date_range = self._format_date_range(item.start_date, item.end_date)
            if date_range:
                lines.append(date_range)
            if item.summary:
                lines.append(item.summary.strip())
            entries.append("\n".join(lines))
        return "\n\n".join(entries)

    def _render_certifications_section(self, certifications: list[MasterCertification]) -> str:
        lines = []
        for item in certifications:
            parts = [f"{item.name} | {item.issuer}"]
            meta = [part for part in [item.issued_on, item.credential_id, item.credential_url] if part]
            if meta:
                parts.append(" | ".join(meta))
            lines.append(" | ".join(parts))
        return "\n".join(f"- {line}" for line in lines)

    def _render_languages_section(self, languages: list[MasterLanguage]) -> str:
        return "\n".join(f"- {item.name} ({item.proficiency})" for item in languages)

    def _build_summary_source(
        self,
        *,
        candidate_profile: CandidateProfile,
        selected_content: SelectedCvContent,
    ) -> str:
        lines = []
        if candidate_profile.summary:
            lines.append(f"Candidate profile summary: {candidate_profile.summary.strip()}")
        if selected_content.work_experiences:
            lines.append("Relevant work experience:")
            for experience in selected_content.work_experiences:
                lines.append(f"- {experience.title} at {experience.company}")
        if selected_content.projects:
            lines.append("Relevant projects:")
            for project in selected_content.projects:
                lines.append(f"- {project.name}")
        return "\n".join(lines).strip()

    def _build_skills_source(self, *, workspace: ResumeWorkspace) -> str:
        return "\n".join(
            f"- {skill.name}{f' ({skill.proficiency_level})' if skill.proficiency_level else ''}{f': {skill.notes}' if skill.notes else ''}"
            for skill in workspace.skills
        )

    def _build_experience_source(self, work_experiences: list[MasterWorkExperience]) -> str:
        lines: list[str] = []
        for experience in work_experiences:
            lines.append(f"{experience.title} | {experience.company}")
            if experience.summary:
                lines.append(f"Context: {experience.summary.strip()}")
            lines.extend(f"- {highlight.strip()}" for highlight in experience.highlights if highlight.strip())
            lines.append("")
        return "\n".join(lines).strip()

    def _build_projects_source(self, projects: list[MasterProject]) -> str:
        lines: list[str] = []
        for project in projects:
            lines.append(project.name)
            if project.role:
                lines.append(project.role.strip())
            if project.summary:
                lines.append(project.summary.strip())
            if project.technologies:
                lines.append(f"Technologies: {', '.join(project.technologies)}")
            lines.append("")
        return "\n".join(lines).strip()

    def _experience_score(self, experience: MasterWorkExperience, job_text: str) -> int:
        text = self._normalize_text(
            " ".join(
                [
                    experience.title,
                    experience.company,
                    experience.location or "",
                    experience.summary or "",
                    " ".join(experience.highlights),
                ]
            )
        )
        return self._overlap_score(text, job_text)

    def _project_score(self, project: MasterProject, job_text: str) -> int:
        text = self._normalize_text(
            " ".join(
                [
                    project.name,
                    project.role or "",
                    project.summary or "",
                    " ".join(project.technologies),
                ]
            )
        )
        return self._overlap_score(text, job_text)

    def _overlap_score(self, source_text: str, job_text: str) -> int:
        source_tokens = set(source_text.split())
        job_tokens = set(job_text.split())
        return sum(1 for token in source_tokens if token in job_tokens and len(token) > 2)

    def _job_text(self, job: JobDetail) -> str:
        snapshot = job.latest_snapshot
        if snapshot is None:
            return ""
        return " ".join(
            part for part in [snapshot.title, snapshot.company, snapshot.location, snapshot.visible_text] if part
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    @staticmethod
    def _format_date_range(start_date: str | None, end_date: str | None) -> str | None:
        if start_date and end_date:
            return f"{start_date} - {end_date}"
        return start_date or end_date


def get_job_cv_generation_service() -> JobCvGenerationService:
    return JobCvGenerationService()
