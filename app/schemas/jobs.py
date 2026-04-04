from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


JobStatus = Literal["new", "in_progress", "applied", "dropped", "archived"]


class StoredJob(BaseModel):
    id: int
    source: str
    external_job_id: str | None
    source_url: HttpUrl
    page_title: str | None
    tentative_job_title: str | None
    status: JobStatus
    created_at: str


class LatestJobSnapshot(BaseModel):
    id: int
    title: str | None
    company: str | None
    location: str | None
    visible_text: str | None
    html: str | None
    plugin_name: str
    captured_at: str


class CompatibilityCheckResult(BaseModel):
    id: int
    resume_profile_id: int
    score: int
    decision: str
    summary: str
    strengths: list[str]
    gaps: list[str]
    raw_model_response: str
    created_at: str


class CandidateCompatibilityCheckResult(BaseModel):
    id: int
    score: int
    short_reason: str
    strengths: list[str]
    gaps: list[str]
    raw_model_response: str
    created_at: str


class JobListItem(StoredJob):
    latest_snapshot: LatestJobSnapshot | None = None
    latest_candidate_compatibility_check: CandidateCompatibilityCheckResult | None = None


class JobDetail(StoredJob):
    latest_snapshot: LatestJobSnapshot | None
    latest_compatibility_check: CompatibilityCheckResult | None
    latest_candidate_compatibility_check: CandidateCompatibilityCheckResult | None


class MasterSkill(BaseModel):
    id: int
    name: str
    proficiency_level: str | None
    notes: str | None
    created_at: str
    updated_at: str


class MasterWorkExperience(BaseModel):
    id: int
    company: str
    title: str
    location: str | None
    start_date: str | None
    end_date: str | None
    summary: str | None
    highlights: list[str]
    created_at: str
    updated_at: str


class MasterProject(BaseModel):
    id: int
    name: str
    role: str | None
    summary: str | None
    technologies: list[str]
    url: str | None
    created_at: str
    updated_at: str


class MasterEducation(BaseModel):
    id: int
    institution: str
    degree: str
    field_of_study: str | None
    start_date: str | None
    end_date: str | None
    summary: str | None
    created_at: str
    updated_at: str


class MasterCertification(BaseModel):
    id: int
    name: str
    issuer: str
    issued_on: str | None
    credential_id: str | None
    credential_url: str | None
    created_at: str
    updated_at: str


class MasterLanguage(BaseModel):
    id: int
    name: str
    proficiency: str
    created_at: str
    updated_at: str


class MasterLink(BaseModel):
    id: int
    label: str
    url: str
    link_type: str | None
    created_at: str
    updated_at: str


class CandidateProfile(BaseModel):
    id: int
    summary: str | None
    created_at: str
    updated_at: str


class ResumeProfile(BaseModel):
    id: int
    name: str
    headline: str | None
    summary: str | None
    content: str
    created_at: str
    updated_at: str


class ResumeProfileSection(BaseModel):
    section_key: str
    label: str
    custom_instructions: str | None
    source_material: str
    generated_content: str | None
    updated_at: str
    generated_at: str | None


class ResumeProfileDetail(ResumeProfile):
    selected_skill_ids: list[int]
    selected_work_experience_ids: list[int]
    selected_project_ids: list[int]
    selected_education_ids: list[int]
    selected_certification_ids: list[int]
    selected_language_ids: list[int]
    sections: list[ResumeProfileSection]


class ResumeWorkspace(BaseModel):
    candidate_profile: CandidateProfile
    skills: list[MasterSkill]
    work_experiences: list[MasterWorkExperience]
    projects: list[MasterProject]
    education: list[MasterEducation]
    certifications: list[MasterCertification]
    languages: list[MasterLanguage]
    links: list[MasterLink]
    resume_profiles: list[ResumeProfile]


class CreateResumeProfileRequest(BaseModel):
    name: str
    content: str | None = None
    headline: str | None = None
    summary: str | None = None
    selected_skill_ids: list[int] = Field(default_factory=list)
    selected_work_experience_ids: list[int] = Field(default_factory=list)
    selected_project_ids: list[int] = Field(default_factory=list)
    selected_education_ids: list[int] = Field(default_factory=list)
    selected_certification_ids: list[int] = Field(default_factory=list)
    selected_language_ids: list[int] = Field(default_factory=list)
    section_instructions: dict[str, str] = Field(default_factory=dict)


class UpdateResumeProfileRequest(CreateResumeProfileRequest):
    pass


class CreateMasterSkillRequest(BaseModel):
    name: str
    proficiency_level: str | None = None
    notes: str | None = None


class UpdateMasterSkillRequest(CreateMasterSkillRequest):
    pass


class CreateMasterWorkExperienceRequest(BaseModel):
    company: str
    title: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None
    highlights: list[str] = Field(default_factory=list)


class UpdateMasterWorkExperienceRequest(CreateMasterWorkExperienceRequest):
    pass


class CreateMasterProjectRequest(BaseModel):
    name: str
    role: str | None = None
    summary: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class UpdateMasterProjectRequest(CreateMasterProjectRequest):
    pass


class CreateMasterEducationRequest(BaseModel):
    institution: str
    degree: str
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None


class UpdateMasterEducationRequest(CreateMasterEducationRequest):
    pass


class CreateMasterCertificationRequest(BaseModel):
    name: str
    issuer: str
    issued_on: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class UpdateMasterCertificationRequest(CreateMasterCertificationRequest):
    pass


class CreateMasterLanguageRequest(BaseModel):
    name: str
    proficiency: str


class UpdateMasterLanguageRequest(CreateMasterLanguageRequest):
    pass


class CreateMasterLinkRequest(BaseModel):
    label: str
    url: str
    link_type: str | None = None


class UpdateMasterLinkRequest(CreateMasterLinkRequest):
    pass


class ImportedResumeWorkExperience(BaseModel):
    company: str
    title: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None
    highlights: list[str] = Field(default_factory=list)


class ImportedResumeProject(BaseModel):
    name: str
    role: str | None = None
    summary: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class ImportedResumeEducation(BaseModel):
    institution: str
    degree: str
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None


class ImportedResumeCertification(BaseModel):
    name: str
    issuer: str
    issued_on: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class ImportedResumeLanguage(BaseModel):
    name: str
    proficiency: str


class ImportedResumeLink(BaseModel):
    label: str
    url: str
    link_type: str | None = None


class ResumeImportPreview(BaseModel):
    filename: str
    raw_text: str
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    work_experiences: list[ImportedResumeWorkExperience] = Field(default_factory=list)
    projects: list[ImportedResumeProject] = Field(default_factory=list)
    education: list[ImportedResumeEducation] = Field(default_factory=list)
    certifications: list[ImportedResumeCertification] = Field(default_factory=list)
    languages: list[ImportedResumeLanguage] = Field(default_factory=list)
    links: list[ImportedResumeLink] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ambiguous_sections: list[str] = Field(default_factory=list)


class ParseResumeImportRequest(BaseModel):
    filename: str
    content_base64: str


class ConfirmResumeImportRequest(BaseModel):
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    work_experiences: list[ImportedResumeWorkExperience] = Field(default_factory=list)
    projects: list[ImportedResumeProject] = Field(default_factory=list)
    education: list[ImportedResumeEducation] = Field(default_factory=list)
    certifications: list[ImportedResumeCertification] = Field(default_factory=list)
    languages: list[ImportedResumeLanguage] = Field(default_factory=list)
    links: list[ImportedResumeLink] = Field(default_factory=list)


class UpdateCandidateProfileRequest(BaseModel):
    summary: str | None = None


class GenerateResumeSummaryRequest(BaseModel):
    job_id: int
    resume_profile_id: int


class GenerateResumeSummaryResponse(BaseModel):
    resume_profile_id: int
    job_id: int
    generated_summary: str


class GenerateResumeSkillsRequest(BaseModel):
    job_id: int
    resume_profile_id: int


class GenerateResumeSkillsResponse(BaseModel):
    resume_profile_id: int
    job_id: int
    generated_skills: list[str]


class ProviderModelOption(BaseModel):
    provider: str
    model_id: str
    label: str
    source: str
    is_free: bool
    last_refreshed_at: str | None = None


class OpenRouterSettings(BaseModel):
    has_api_key: bool
    masked_api_key: str | None
    api_key_source: str
    saved_provider: str | None
    effective_provider: str
    saved_default_model: str | None
    effective_default_model: str | None
    updated_at: str | None


class UpdateOpenRouterSettingsRequest(BaseModel):
    api_key: str | None = None
    provider: str | None = None
    default_model: str | None = None


class SettingsModelsResponse(BaseModel):
    providers: list[str]
    models: list[ProviderModelOption]
    updated_at: str | None


class PromptSettings(BaseModel):
    summary_prompt: str | None = None
    skills_prompt: str | None = None
    experience_prompt: str | None = None
    projects_prompt: str | None = None
    updated_at: str | None = None


class UpdatePromptSettingsRequest(BaseModel):
    summary_prompt: str | None = None
    skills_prompt: str | None = None
    experience_prompt: str | None = None
    projects_prompt: str | None = None


class RunCompatibilityCheckRequest(BaseModel):
    resume_profile_id: int


class RunCompatibilityCheckResponse(BaseModel):
    job_id: int
    compatibility_check: CompatibilityCheckResult


class RunCandidateCompatibilityCheckResponse(BaseModel):
    job_id: int
    compatibility_check: CandidateCompatibilityCheckResult


class UpdateJobStatusRequest(BaseModel):
    status: JobStatus


JobCheckBatchMode = Literal["all", "unscored"]
JobCheckBatchStatus = Literal["running", "completed", "failed", "cancelled"]
JobCheckBatchItemStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class StartJobCheckBatchRequest(BaseModel):
    mode: JobCheckBatchMode


class JobCheckBatchItem(BaseModel):
    id: int
    batch_id: int
    job_id: int
    status: JobCheckBatchItemStatus
    error_message: str | None = None
    updated_at: str


class JobCheckBatchRun(BaseModel):
    id: int
    mode: JobCheckBatchMode
    status: JobCheckBatchStatus
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    created_at: str
    updated_at: str
    last_error: str | None = None
    items: list[JobCheckBatchItem] = Field(default_factory=list)
