from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.persistence.sqlite import SQLiteJobStore, get_job_store
from app.schemas.jobs import (
    CandidateProfile,
    ConfirmResumeImportRequest,
    CreateMasterCertificationRequest,
    CreateMasterEducationRequest,
    CreateMasterLanguageRequest,
    CreateMasterLinkRequest,
    CreateMasterProjectRequest,
    CreateMasterSkillRequest,
    CreateMasterWorkExperienceRequest,
    CreateResumeProfileRequest,
    GenerateResumeSkillsRequest,
    GenerateResumeSkillsResponse,
    GenerateResumeSummaryRequest,
    GenerateResumeSummaryResponse,
    MasterLink,
    MasterCertification,
    MasterEducation,
    MasterLanguage,
    MasterProject,
    MasterSkill,
    MasterWorkExperience,
    ParseResumeImportRequest,
    ResumeProfile,
    ResumeImportPreview,
    ResumeProfileDetail,
    ResumeWorkspace,
    UpdateCandidateProfileRequest,
    UpdateMasterCertificationRequest,
    UpdateMasterEducationRequest,
    UpdateMasterLanguageRequest,
    UpdateMasterLinkRequest,
    UpdateMasterProjectRequest,
    UpdateMasterSkillRequest,
    UpdateMasterWorkExperienceRequest,
    UpdateResumeProfileRequest,
)
from app.services.resume_import import parse_resume_upload
from app.services.resume_summary_generation import get_summary_generation_service
from app.services.compatibility_errors import (
    CompatibilityProviderConfigurationError,
    CompatibilityProviderRequestError,
    CompatibilityProviderResponseError,
    CompatibilityProviderTimeoutError,
)


router = APIRouter(tags=["resume-profiles"])


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/resume-profiles", response_model=list[ResumeProfile])
def list_resume_profiles(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[ResumeProfile]:
    return job_store.list_resume_profiles()


@router.get("/resume-profiles/workspace", response_model=ResumeWorkspace)
def get_resume_workspace(job_store: SQLiteJobStore = Depends(get_job_store)) -> ResumeWorkspace:
    return job_store.get_resume_workspace()


@router.get("/candidate-profile", response_model=CandidateProfile)
def get_candidate_profile(job_store: SQLiteJobStore = Depends(get_job_store)) -> CandidateProfile:
    return job_store.get_candidate_profile()


@router.put("/candidate-profile", response_model=CandidateProfile)
def update_candidate_profile(
    payload: UpdateCandidateProfileRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> CandidateProfile:
    return job_store.update_candidate_profile(payload)


@router.get("/resume-profiles/{resume_profile_id}", response_model=ResumeProfileDetail)
def get_resume_profile(
    resume_profile_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> ResumeProfileDetail:
    profile = job_store.get_resume_profile_detail(resume_profile_id)
    if profile is None:
        raise _not_found("Resume profile not found.")
    return profile


@router.post("/resume-profiles", response_model=ResumeProfileDetail, status_code=status.HTTP_201_CREATED)
def create_resume_profile(
    payload: CreateResumeProfileRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> ResumeProfileDetail:
    try:
        return job_store.create_resume_profile(
            name=payload.name,
            headline=payload.headline,
            summary=payload.summary,
            content=payload.content,
            section_instructions=payload.section_instructions,
            selected_skill_ids=payload.selected_skill_ids,
            selected_work_experience_ids=payload.selected_work_experience_ids,
            selected_project_ids=payload.selected_project_ids,
            selected_education_ids=payload.selected_education_ids,
            selected_certification_ids=payload.selected_certification_ids,
            selected_language_ids=payload.selected_language_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/resume-profiles/{resume_profile_id}/generate-summary", response_model=GenerateResumeSummaryResponse)
def generate_resume_summary(
    resume_profile_id: int,
    payload: GenerateResumeSummaryRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> GenerateResumeSummaryResponse:
    if payload.resume_profile_id != resume_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path resume profile id does not match payload resume_profile_id.",
        )

    job = job_store.get_job_detail(payload.job_id)
    if job is None:
        raise _not_found("Job not found.")

    resume_profile = job_store.get_resume_profile_detail(payload.resume_profile_id)
    if resume_profile is None:
        raise _not_found("Resume profile not found.")

    try:
        result = get_summary_generation_service().generate_summary(
            job=job,
            resume_profile=resume_profile,
            job_store=job_store,
        )
    except CompatibilityProviderConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
    except CompatibilityProviderTimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Summary generation timed out.") from error
    except CompatibilityProviderResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except CompatibilityProviderRequestError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    return GenerateResumeSummaryResponse(
        resume_profile_id=resume_profile_id,
        job_id=payload.job_id,
        generated_summary=result.generated_summary,
    )


@router.post("/resume-profiles/{resume_profile_id}/generate-skills", response_model=GenerateResumeSkillsResponse)
def generate_resume_skills(
    resume_profile_id: int,
    payload: GenerateResumeSkillsRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> GenerateResumeSkillsResponse:
    if payload.resume_profile_id != resume_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path resume profile id does not match payload resume_profile_id.",
        )

    job = job_store.get_job_detail(payload.job_id)
    if job is None:
        raise _not_found("Job not found.")

    resume_profile = job_store.get_resume_profile_detail(payload.resume_profile_id)
    if resume_profile is None:
        raise _not_found("Resume profile not found.")

    try:
        result = get_summary_generation_service().generate_skills(
            job=job,
            resume_profile=resume_profile,
            job_store=job_store,
        )
    except CompatibilityProviderConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
    except CompatibilityProviderTimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Skills generation timed out.") from error
    except CompatibilityProviderResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except CompatibilityProviderRequestError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    return GenerateResumeSkillsResponse(
        resume_profile_id=resume_profile_id,
        job_id=payload.job_id,
        generated_skills=result.generated_skills,
    )


@router.put("/resume-profiles/{resume_profile_id}", response_model=ResumeProfileDetail)
def update_resume_profile(
    resume_profile_id: int,
    payload: UpdateResumeProfileRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> ResumeProfileDetail:
    try:
        profile = job_store.update_resume_profile(
            resume_profile_id,
            name=payload.name,
            headline=payload.headline,
            summary=payload.summary,
            content=payload.content,
            section_instructions=payload.section_instructions,
            selected_skill_ids=payload.selected_skill_ids,
            selected_work_experience_ids=payload.selected_work_experience_ids,
            selected_project_ids=payload.selected_project_ids,
            selected_education_ids=payload.selected_education_ids,
            selected_certification_ids=payload.selected_certification_ids,
            selected_language_ids=payload.selected_language_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if profile is None:
        raise _not_found("Resume profile not found.")
    return profile


@router.delete("/resume-profiles/{resume_profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume_profile(
    resume_profile_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> Response:
    if not job_store.delete_resume_profile(resume_profile_id):
        raise _not_found("Resume profile not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/skills", response_model=list[MasterSkill])
def list_master_skills(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterSkill]:
    return job_store.list_master_skills()


@router.post("/resume-data/skills", response_model=MasterSkill, status_code=status.HTTP_201_CREATED)
def create_master_skill(
    payload: CreateMasterSkillRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterSkill:
    return job_store.create_master_skill(payload)


@router.put("/resume-data/skills/{skill_id}", response_model=MasterSkill)
def update_master_skill(
    skill_id: int,
    payload: UpdateMasterSkillRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterSkill:
    item = job_store.update_master_skill(skill_id, payload)
    if item is None:
        raise _not_found("Skill not found.")
    return item


@router.delete("/resume-data/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_skill(skill_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> Response:
    if not job_store.delete_master_skill(skill_id):
        raise _not_found("Skill not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/work-experiences", response_model=list[MasterWorkExperience])
def list_master_work_experiences(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterWorkExperience]:
    return job_store.list_master_work_experiences()


@router.post("/resume-data/work-experiences", response_model=MasterWorkExperience, status_code=status.HTTP_201_CREATED)
def create_master_work_experience(
    payload: CreateMasterWorkExperienceRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterWorkExperience:
    return job_store.create_master_work_experience(payload)


@router.put("/resume-data/work-experiences/{experience_id}", response_model=MasterWorkExperience)
def update_master_work_experience(
    experience_id: int,
    payload: UpdateMasterWorkExperienceRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterWorkExperience:
    item = job_store.update_master_work_experience(experience_id, payload)
    if item is None:
        raise _not_found("Work experience not found.")
    return item


@router.delete("/resume-data/work-experiences/{experience_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_work_experience(
    experience_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> Response:
    if not job_store.delete_master_work_experience(experience_id):
        raise _not_found("Work experience not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/projects", response_model=list[MasterProject])
def list_master_projects(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterProject]:
    return job_store.list_master_projects()


@router.post("/resume-data/projects", response_model=MasterProject, status_code=status.HTTP_201_CREATED)
def create_master_project(
    payload: CreateMasterProjectRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterProject:
    return job_store.create_master_project(payload)


@router.put("/resume-data/projects/{project_id}", response_model=MasterProject)
def update_master_project(
    project_id: int,
    payload: UpdateMasterProjectRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterProject:
    item = job_store.update_master_project(project_id, payload)
    if item is None:
        raise _not_found("Project not found.")
    return item


@router.delete("/resume-data/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_project(project_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> Response:
    if not job_store.delete_master_project(project_id):
        raise _not_found("Project not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/education", response_model=list[MasterEducation])
def list_master_education(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterEducation]:
    return job_store.list_master_education()


@router.post("/resume-data/education", response_model=MasterEducation, status_code=status.HTTP_201_CREATED)
def create_master_education(
    payload: CreateMasterEducationRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterEducation:
    return job_store.create_master_education(payload)


@router.put("/resume-data/education/{education_id}", response_model=MasterEducation)
def update_master_education(
    education_id: int,
    payload: UpdateMasterEducationRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterEducation:
    item = job_store.update_master_education(education_id, payload)
    if item is None:
        raise _not_found("Education entry not found.")
    return item


@router.delete("/resume-data/education/{education_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_education(education_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> Response:
    if not job_store.delete_master_education(education_id):
        raise _not_found("Education entry not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/certifications", response_model=list[MasterCertification])
def list_master_certifications(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterCertification]:
    return job_store.list_master_certifications()


@router.post("/resume-data/certifications", response_model=MasterCertification, status_code=status.HTTP_201_CREATED)
def create_master_certification(
    payload: CreateMasterCertificationRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterCertification:
    return job_store.create_master_certification(payload)


@router.put("/resume-data/certifications/{certification_id}", response_model=MasterCertification)
def update_master_certification(
    certification_id: int,
    payload: UpdateMasterCertificationRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterCertification:
    item = job_store.update_master_certification(certification_id, payload)
    if item is None:
        raise _not_found("Certification not found.")
    return item


@router.delete("/resume-data/certifications/{certification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_certification(
    certification_id: int,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> Response:
    if not job_store.delete_master_certification(certification_id):
        raise _not_found("Certification not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/languages", response_model=list[MasterLanguage])
def list_master_languages(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterLanguage]:
    return job_store.list_master_languages()


@router.post("/resume-data/languages", response_model=MasterLanguage, status_code=status.HTTP_201_CREATED)
def create_master_language(
    payload: CreateMasterLanguageRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterLanguage:
    return job_store.create_master_language(payload)


@router.put("/resume-data/languages/{language_id}", response_model=MasterLanguage)
def update_master_language(
    language_id: int,
    payload: UpdateMasterLanguageRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterLanguage:
    item = job_store.update_master_language(language_id, payload)
    if item is None:
        raise _not_found("Language not found.")
    return item


@router.delete("/resume-data/languages/{language_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_language(language_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> Response:
    if not job_store.delete_master_language(language_id):
        raise _not_found("Language not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume-data/links", response_model=list[MasterLink])
def list_master_links(job_store: SQLiteJobStore = Depends(get_job_store)) -> list[MasterLink]:
    return job_store.list_master_links()


@router.post("/resume-data/links", response_model=MasterLink, status_code=status.HTTP_201_CREATED)
def create_master_link(
    payload: CreateMasterLinkRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterLink:
    return job_store.create_master_link(payload)


@router.put("/resume-data/links/{link_id}", response_model=MasterLink)
def update_master_link(
    link_id: int,
    payload: UpdateMasterLinkRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> MasterLink:
    item = job_store.update_master_link(link_id, payload)
    if item is None:
        raise _not_found("Link not found.")
    return item


@router.delete("/resume-data/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_master_link(link_id: int, job_store: SQLiteJobStore = Depends(get_job_store)) -> Response:
    if not job_store.delete_master_link(link_id):
        raise _not_found("Link not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/resume-import/parse", response_model=ResumeImportPreview)
def parse_resume_import(payload: ParseResumeImportRequest) -> ResumeImportPreview:
    try:
        return parse_resume_upload(payload.filename, payload.content_base64)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/resume-import/confirm", response_model=ResumeWorkspace)
def confirm_resume_import(
    payload: ConfirmResumeImportRequest,
    job_store: SQLiteJobStore = Depends(get_job_store),
) -> ResumeWorkspace:
    if payload.summary:
        job_store.update_candidate_profile(UpdateCandidateProfileRequest(summary=payload.summary))
    for skill in payload.skills:
        job_store.create_master_skill(CreateMasterSkillRequest(name=skill))
    for item in payload.work_experiences:
        job_store.create_master_work_experience(
            CreateMasterWorkExperienceRequest(
                company=item.company,
                title=item.title,
                location=item.location,
                start_date=item.start_date,
                end_date=item.end_date,
                summary=item.summary,
                highlights=item.highlights,
            )
        )
    for item in payload.projects:
        job_store.create_master_project(
            CreateMasterProjectRequest(
                name=item.name,
                role=item.role,
                summary=item.summary,
                technologies=item.technologies,
                url=item.url,
            )
        )
    for item in payload.education:
        job_store.create_master_education(
            CreateMasterEducationRequest(
                institution=item.institution,
                degree=item.degree,
                field_of_study=item.field_of_study,
                start_date=item.start_date,
                end_date=item.end_date,
                summary=item.summary,
            )
        )
    for item in payload.certifications:
        job_store.create_master_certification(
            CreateMasterCertificationRequest(
                name=item.name,
                issuer=item.issuer,
                issued_on=item.issued_on,
                credential_id=item.credential_id,
                credential_url=item.credential_url,
            )
        )
    for item in payload.languages:
        job_store.create_master_language(
            CreateMasterLanguageRequest(name=item.name, proficiency=item.proficiency)
        )
    for item in payload.links:
        job_store.create_master_link(
            CreateMasterLinkRequest(label=item.label, url=item.url, link_type=item.link_type)
        )
    return job_store.get_resume_workspace()
