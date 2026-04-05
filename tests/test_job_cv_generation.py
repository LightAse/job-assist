from app.schemas.jobs import (
    CandidateProfile,
    JobDetail,
    LatestJobSnapshot,
    MasterProject,
    MasterWorkExperience,
    ResumeWorkspace,
)
from app.services.job_cv_generation import JobCvGenerationService


def _candidate_profile() -> CandidateProfile:
    return CandidateProfile(
        id=1,
        full_name="Jane Doe",
        email="jane@example.com",
        phone="+1 555 010 1234",
        location="Austin, TX",
        linkedin_url="https://linkedin.com/in/jane",
        github_url="https://github.com/jane",
        portfolio_url="https://jane.dev",
        summary="Backend engineer.",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _job_detail(visible_text: str) -> JobDetail:
    return JobDetail(
        id=30,
        source="linkedin",
        external_job_id="12345",
        source_url="https://www.linkedin.com/jobs/view/12345/",
        page_title="Job",
        tentative_job_title="Job",
        status="new",
        created_at="2026-01-01T00:00:00+00:00",
        latest_snapshot=LatestJobSnapshot(
            id=1,
            title="Platform Engineer",
            company="Example Co",
            location="Remote",
            visible_text=visible_text,
            html=None,
            plugin_name="linkedin_job_scraper",
            captured_at="2026-01-01T00:00:00+00:00",
        ),
        latest_compatibility_check=None,
        latest_candidate_compatibility_check=None,
        generated_cvs=[],
    )


def _work_experience(
    *,
    item_id: int,
    company: str,
    title: str,
    summary: str,
    highlights: list[str],
) -> MasterWorkExperience:
    return MasterWorkExperience(
        id=item_id,
        company=company,
        title=title,
        location=None,
        start_date=None,
        end_date=None,
        summary=summary,
        highlights=highlights,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _project(
    *,
    item_id: int,
    name: str,
    summary: str,
    technologies: list[str],
) -> MasterProject:
    return MasterProject(
        id=item_id,
        name=name,
        role="Builder",
        summary=summary,
        technologies=technologies,
        url=None,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _workspace(*, work_experiences: list[MasterWorkExperience], projects: list[MasterProject]) -> ResumeWorkspace:
    return ResumeWorkspace(
        candidate_profile=_candidate_profile(),
        skills=[],
        work_experiences=work_experiences,
        projects=projects,
        education=[],
        certifications=[],
        languages=[],
        links=[],
        resume_profiles=[],
    )


def test_select_relevant_content_prefers_stronger_project_over_weak_work_experience() -> None:
    service = JobCvGenerationService()
    selected = service._select_relevant_content(
        job=_job_detail("Platform Engineer Terraform Kubernetes CI/CD automation"),
        workspace=_workspace(
            work_experiences=[
                _work_experience(
                    item_id=1,
                    company="Retail Co",
                    title="Store Associate",
                    summary="Handled in-store operations.",
                    highlights=["Customer support", "Cash handling"],
                )
            ],
            projects=[
                _project(
                    item_id=1,
                    name="Kubernetes Platform Automation",
                    summary="Built Terraform and Kubernetes automation pipelines.",
                    technologies=["Terraform", "Kubernetes", "CI/CD"],
                )
            ],
        ),
    )

    assert selected.work_experiences == []
    assert [project.name for project in selected.projects] == ["Kubernetes Platform Automation"]


def test_select_relevant_content_keeps_stronger_work_experience_prioritized() -> None:
    service = JobCvGenerationService()
    selected = service._select_relevant_content(
        job=_job_detail("Senior Backend Engineer Python FastAPI Postgres APIs"),
        workspace=_workspace(
            work_experiences=[
                _work_experience(
                    item_id=1,
                    company="Example Co",
                    title="Senior Backend Engineer",
                    summary="Built Python and FastAPI APIs backed by Postgres.",
                    highlights=["Designed API services", "Optimized Postgres queries"],
                )
            ],
            projects=[
                _project(
                    item_id=1,
                    name="Personal Portfolio",
                    summary="A static website project.",
                    technologies=["HTML", "CSS"],
                )
            ],
        ),
    )

    assert [experience.title for experience in selected.work_experiences] == ["Senior Backend Engineer"]
    assert selected.projects == []


def test_select_relevant_content_includes_both_when_both_are_competitive() -> None:
    service = JobCvGenerationService()
    selected = service._select_relevant_content(
        job=_job_detail("Backend Platform Engineer Python FastAPI Kubernetes Postgres"),
        workspace=_workspace(
            work_experiences=[
                _work_experience(
                    item_id=1,
                    company="Example Co",
                    title="Backend Engineer",
                    summary="Built Python and FastAPI services with Postgres.",
                    highlights=["API design", "Database tuning"],
                )
            ],
            projects=[
                _project(
                    item_id=1,
                    name="Platform Automation",
                    summary="Built Kubernetes automation for service delivery.",
                    technologies=["Kubernetes", "Python"],
                )
            ],
        ),
    )

    assert [experience.title for experience in selected.work_experiences] == ["Backend Engineer"]
    assert [project.name for project in selected.projects] == ["Platform Automation"]
