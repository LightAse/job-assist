import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.jobs import (
    CandidateCompatibilityCheckResult,
    CompatibilityCheckResult,
    CandidateProfile,
    CreateMasterCertificationRequest,
    CreateMasterEducationRequest,
    CreateMasterLanguageRequest,
    CreateMasterLinkRequest,
    CreateMasterProjectRequest,
    CreateMasterSkillRequest,
    CreateMasterWorkExperienceRequest,
    JobDetail,
    JobCheckBatchItem,
    JobCheckBatchRun,
    JobListItem,
    LatestJobSnapshot,
    MasterCertification,
    MasterEducation,
    MasterLanguage,
    MasterLink,
    MasterProject,
    MasterSkill,
    MasterWorkExperience,
    OpenRouterSettings,
    PromptSettings,
    ProviderModelOption,
    ResumeProfile,
    ResumeProfileDetail,
    ResumeProfileSection,
    ResumeWorkspace,
    StartJobCheckBatchRequest,
    StoredJob,
    UpdateCandidateProfileRequest,
    UpdateMasterCertificationRequest,
    UpdateMasterEducationRequest,
    UpdateMasterLanguageRequest,
    UpdateMasterLinkRequest,
    UpdateMasterProjectRequest,
    UpdateMasterSkillRequest,
    UpdateMasterWorkExperienceRequest,
    UpdateOpenRouterSettingsRequest,
    UpdatePromptSettingsRequest,
)
from app.schemas.scrape import ScrapeContext, ScrapeCurrentResponse


def _default_database_path() -> Path:
    configured_path = os.environ.get("JOB_ASSIST_DB_PATH")
    if configured_path:
        return Path(configured_path)
    return Path("data/job_assist.db")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PersistedScrapeRecord:
    job_id: int
    snapshot_id: int | None
    status: str
    deduplicated: bool
    reason: str | None = None


class SQLiteJobStore:
    _resume_section_labels = {
        "summary": "Summary / About Me",
        "skills": "Selected Skills",
        "experience": "Experience Bullets",
        "projects": "Selected Projects",
        "education": "Education",
        "certifications": "Certifications",
        "languages": "Languages",
    }
    _seed_model_registry = [
        ProviderModelOption(provider="openrouter", model_id="minimax/minimax-m2.5:free", label="MiniMax M2.5 (free)", source="seed", is_free=True),
        ProviderModelOption(provider="openrouter", model_id="qwen/qwen3.6-plus:free", label="Qwen3.6 Plus (free)", source="seed", is_free=True),
        ProviderModelOption(provider="openrouter", model_id="qwen/qwen3.6-plus-preview:free", label="Qwen3.6 Plus Preview (free)", source="seed", is_free=True),
        ProviderModelOption(provider="openrouter", model_id="nvidia/nemotron-3-super-120b-a12b:free", label="Nemotron 3 Super (free)", source="seed", is_free=True),
        ProviderModelOption(provider="openrouter", model_id="openai/gpt-5-nano", label="GPT-5 Nano", source="seed", is_free=False),
        ProviderModelOption(provider="openrouter", model_id="xiaomi/mimo-v2-pro", label="MiMo-V2-Pro", source="seed", is_free=False),
        ProviderModelOption(provider="openrouter", model_id="xiaomi/mimo-v2-omni", label="MiMo-V2-Omni", source="seed", is_free=False),
    ]

    def __init__(self, database_path: str | Path | None = None) -> None:
        self._database_path = Path(database_path) if database_path is not None else _default_database_path()
        self._ensure_parent_directory()
        self._initialize_schema()

    @property
    def database_path(self) -> Path:
        return self._database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            connection.row_factory = sqlite3.Row
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_parent_directory(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    external_job_id TEXT,
                    source_url TEXT NOT NULL,
                    page_title TEXT,
                    tentative_job_title TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    html TEXT,
                    visible_text TEXT,
                    plugin_name TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    headline TEXT,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS candidate_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS opencode_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    api_key TEXT,
                    provider TEXT,
                    default_model TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prompt_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    summary_prompt TEXT,
                    skills_prompt TEXT,
                    experience_prompt TEXT,
                    projects_prompt TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS opencode_model_registry (
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    source TEXT NOT NULL,
                    is_free INTEGER NOT NULL DEFAULT 0,
                    last_refreshed_at TEXT NOT NULL,
                    PRIMARY KEY (provider, model_id)
                );

                CREATE TABLE IF NOT EXISTS master_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    proficiency_level TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS master_work_experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    summary TEXT,
                    highlights_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS master_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    role TEXT,
                    summary TEXT,
                    technologies_json TEXT NOT NULL,
                    url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS master_education (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    institution TEXT NOT NULL,
                    degree TEXT NOT NULL,
                    field_of_study TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS master_certifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    issued_on TEXT,
                    credential_id TEXT,
                    credential_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS master_languages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    proficiency TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS master_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    url TEXT NOT NULL,
                    link_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS resume_profile_selected_skills (
                    resume_profile_id INTEGER NOT NULL,
                    skill_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (resume_profile_id, skill_id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id),
                    FOREIGN KEY (skill_id) REFERENCES master_skills (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profile_selected_work_experiences (
                    resume_profile_id INTEGER NOT NULL,
                    work_experience_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (resume_profile_id, work_experience_id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id),
                    FOREIGN KEY (work_experience_id) REFERENCES master_work_experiences (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profile_selected_projects (
                    resume_profile_id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (resume_profile_id, project_id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id),
                    FOREIGN KEY (project_id) REFERENCES master_projects (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profile_selected_education (
                    resume_profile_id INTEGER NOT NULL,
                    education_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (resume_profile_id, education_id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id),
                    FOREIGN KEY (education_id) REFERENCES master_education (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profile_selected_certifications (
                    resume_profile_id INTEGER NOT NULL,
                    certification_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (resume_profile_id, certification_id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id),
                    FOREIGN KEY (certification_id) REFERENCES master_certifications (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profile_selected_languages (
                    resume_profile_id INTEGER NOT NULL,
                    language_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY (resume_profile_id, language_id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id),
                    FOREIGN KEY (language_id) REFERENCES master_languages (id)
                );

                CREATE TABLE IF NOT EXISTS resume_profile_sections (
                    resume_profile_id INTEGER NOT NULL,
                    section_key TEXT NOT NULL,
                    custom_instructions TEXT,
                    source_material TEXT NOT NULL,
                    generated_content TEXT,
                    updated_at TEXT NOT NULL,
                    generated_at TEXT,
                    PRIMARY KEY (resume_profile_id, section_key),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id)
                );

                CREATE TABLE IF NOT EXISTS compatibility_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    snapshot_id INTEGER NOT NULL,
                    resume_profile_id INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    strengths_json TEXT NOT NULL,
                    gaps_json TEXT NOT NULL,
                    raw_model_response TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs (id),
                    FOREIGN KEY (snapshot_id) REFERENCES job_snapshots (id),
                    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles (id)
                );

                CREATE TABLE IF NOT EXISTS candidate_compatibility_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    snapshot_id INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    short_reason TEXT NOT NULL,
                    strengths_json TEXT NOT NULL,
                    gaps_json TEXT NOT NULL,
                    raw_model_response TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs (id),
                    FOREIGN KEY (snapshot_id) REFERENCES job_snapshots (id)
                );

                CREATE TABLE IF NOT EXISTS job_check_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_jobs INTEGER NOT NULL,
                    completed_jobs INTEGER NOT NULL DEFAULT 0,
                    failed_jobs INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_check_batch_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    job_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (batch_id) REFERENCES job_check_batches (id),
                    FOREIGN KEY (job_id) REFERENCES jobs (id)
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_source_external_job_id
                ON jobs (source, external_job_id);

                CREATE INDEX IF NOT EXISTS idx_jobs_source_url
                ON jobs (source_url);

                CREATE INDEX IF NOT EXISTS idx_job_snapshots_job_id
                ON job_snapshots (job_id);

                CREATE INDEX IF NOT EXISTS idx_job_check_batch_items_batch_id
                ON job_check_batch_items (batch_id);
                """
            )
            self._ensure_column(connection, "job_snapshots", "company", "TEXT")
            self._ensure_column(connection, "job_snapshots", "location", "TEXT")
            self._ensure_column(connection, "jobs", "status", "TEXT NOT NULL DEFAULT 'new'")
            self._ensure_column(connection, "resume_profiles", "headline", "TEXT")
            self._ensure_column(connection, "resume_profiles", "summary", "TEXT")
            self._ensure_column(connection, "resume_profiles", "updated_at", "TEXT")
            self._ensure_column(connection, "opencode_settings", "provider", "TEXT")
            connection.execute(
                """
                UPDATE jobs
                SET status = 'new'
                WHERE status IS NULL OR TRIM(status) = ''
                """
            )
            connection.execute(
                """
                UPDATE resume_profiles
                SET updated_at = COALESCE(updated_at, created_at)
                WHERE updated_at IS NULL
                """
            )
            now = _utc_now_iso()
            connection.execute(
                """
                INSERT INTO candidate_profile (id, summary, created_at, updated_at)
                SELECT 1, NULL, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM candidate_profile WHERE id = 1)
                """,
                (now, now),
            )
            connection.execute(
                """
                INSERT INTO opencode_settings (id, api_key, provider, default_model, updated_at)
                SELECT 1, NULL, 'openrouter', NULL, ?
                WHERE NOT EXISTS (SELECT 1 FROM opencode_settings WHERE id = 1)
                """,
                (now,),
            )
            connection.execute(
                """
                INSERT INTO prompt_settings (id, summary_prompt, skills_prompt, experience_prompt, projects_prompt, updated_at)
                SELECT 1, NULL, NULL, NULL, NULL, ?
                WHERE NOT EXISTS (SELECT 1 FROM prompt_settings WHERE id = 1)
                """,
                (now,),
            )
            self._seed_openrouter_model_registry(connection)

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def save_matched_scrape(
        self,
        context: ScrapeContext,
        scrape_result: ScrapeCurrentResponse,
    ) -> PersistedScrapeRecord:
        structured_data = scrape_result.structured_data
        source = structured_data.get("source") or "generic"
        external_job_id = structured_data.get("external_job_id")
        dedupe_title = context.title or structured_data.get("page_title") or structured_data.get("tentative_job_title")
        dedupe_company = context.company
        timestamp = _utc_now_iso()

        with self._connect() as connection:
            existing_job_id = self._find_existing_job_id(
                connection,
                source=source,
                external_job_id=external_job_id,
                source_url=str(scrape_result.source_url),
                title=dedupe_title,
                company=dedupe_company,
            )
            if existing_job_id is not None:
                return PersistedScrapeRecord(
                    job_id=existing_job_id,
                    snapshot_id=None,
                    status="skipped",
                    deduplicated=True,
                    reason="duplicate",
                )

            job_cursor = connection.execute(
                """
                INSERT INTO jobs (
                    source,
                    external_job_id,
                    source_url,
                    page_title,
                    tentative_job_title,
                    status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    external_job_id,
                    str(scrape_result.source_url),
                    structured_data.get("page_title"),
                    structured_data.get("tentative_job_title"),
                    "new",
                    timestamp,
                ),
            )
            job_id = int(job_cursor.lastrowid)

            snapshot_cursor = connection.execute(
                """
                INSERT INTO job_snapshots (
                    job_id,
                    source_url,
                    title,
                    company,
                    location,
                    html,
                    visible_text,
                    plugin_name,
                    captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(context.url),
                    context.title,
                    context.company,
                    context.location,
                    context.html,
                    context.visible_text,
                    scrape_result.plugin_name,
                    timestamp,
                ),
            )

        return PersistedScrapeRecord(
            job_id=job_id,
            snapshot_id=int(snapshot_cursor.lastrowid),
            status="created",
            deduplicated=False,
        )

    def persist_matched_scrape(
        self,
        context: ScrapeContext,
        scrape_result: ScrapeCurrentResponse,
    ) -> ScrapeCurrentResponse:
        record = self.save_matched_scrape(context, scrape_result)
        return scrape_result.model_copy(
            update={
                "status": record.status,
                "job_id": record.job_id,
                "deduplicated": record.deduplicated,
                "reason": record.reason,
            }
        )

    def list_jobs(self) -> list[JobListItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    jobs.id,
                    jobs.source,
                    jobs.external_job_id,
                    jobs.source_url,
                    jobs.page_title,
                    jobs.tentative_job_title,
                    jobs.status,
                    jobs.created_at,
                    snapshots.id AS latest_snapshot_id,
                    snapshots.title AS latest_snapshot_title,
                    snapshots.company AS latest_snapshot_company,
                    snapshots.location AS latest_snapshot_location,
                    snapshots.visible_text AS latest_snapshot_visible_text,
                    snapshots.html AS latest_snapshot_html,
                    snapshots.plugin_name AS latest_snapshot_plugin_name,
                    snapshots.captured_at AS latest_snapshot_captured_at,
                    candidate_checks.id AS latest_candidate_check_id,
                    candidate_checks.score AS latest_candidate_check_score,
                    candidate_checks.short_reason AS latest_candidate_check_short_reason,
                    candidate_checks.strengths_json AS latest_candidate_check_strengths_json,
                    candidate_checks.gaps_json AS latest_candidate_check_gaps_json,
                    candidate_checks.raw_model_response AS latest_candidate_check_raw_model_response,
                    candidate_checks.created_at AS latest_candidate_check_created_at
                FROM jobs
                LEFT JOIN job_snapshots AS snapshots
                    ON snapshots.id = (
                        SELECT id
                        FROM job_snapshots
                        WHERE job_id = jobs.id
                        ORDER BY captured_at DESC, id DESC
                        LIMIT 1
                    )
                LEFT JOIN candidate_compatibility_checks AS candidate_checks
                    ON candidate_checks.id = (
                        SELECT id
                        FROM candidate_compatibility_checks
                        WHERE job_id = jobs.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    )
                ORDER BY jobs.created_at DESC, jobs.id DESC
                """
            ).fetchall()

        return [self._row_to_job_list_item(row) for row in rows]

    def get_job(self, job_id: int) -> StoredJob | None:
        row = self._get_job_row(job_id)
        if row is None:
            return None
        return self._row_to_stored_job(row)

    def get_job_detail(self, job_id: int) -> JobDetail | None:
        job_row = self._get_job_row(job_id)
        if job_row is None:
            return None

        with self._connect() as connection:
            snapshot_row = connection.execute(
                """
                SELECT
                    id,
                    title,
                    company,
                    location,
                    visible_text,
                    html,
                    plugin_name,
                    captured_at
                FROM job_snapshots
                WHERE job_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            compatibility_row = connection.execute(
                """
                SELECT
                    id,
                    resume_profile_id,
                    score,
                    decision,
                    summary,
                    strengths_json,
                    gaps_json,
                    raw_model_response,
                    created_at
                FROM compatibility_checks
                WHERE job_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            candidate_compatibility_row = connection.execute(
                """
                SELECT
                    id,
                    score,
                    short_reason,
                    strengths_json,
                    gaps_json,
                    raw_model_response,
                    created_at
                FROM candidate_compatibility_checks
                WHERE job_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()

        return JobDetail(
            **self._row_to_stored_job(job_row).model_dump(),
            latest_snapshot=self._row_to_latest_snapshot(snapshot_row) if snapshot_row else None,
            latest_compatibility_check=self._row_to_compatibility_check(compatibility_row) if compatibility_row else None,
            latest_candidate_compatibility_check=self._row_to_candidate_compatibility_check(candidate_compatibility_row) if candidate_compatibility_row else None,
        )

    def update_job_status(self, job_id: int, status_value: str) -> StoredJob | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?
                WHERE id = ?
                """,
                (status_value, job_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT
                    id,
                    source,
                    external_job_id,
                    source_url,
                    page_title,
                    tentative_job_title,
                    status,
                    created_at
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return self._row_to_stored_job(row) if row else None

    def create_resume_profile(
        self,
        *,
        name: str,
        headline: str | None = None,
        summary: str | None = None,
        content: str | None = None,
        section_instructions: dict[str, str] | None = None,
        selected_skill_ids: list[int] | None = None,
        selected_work_experience_ids: list[int] | None = None,
        selected_project_ids: list[int] | None = None,
        selected_education_ids: list[int] | None = None,
        selected_certification_ids: list[int] | None = None,
        selected_language_ids: list[int] | None = None,
    ) -> ResumeProfileDetail:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO resume_profiles (name, headline, summary, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, headline, summary, content or "", timestamp, timestamp),
            )
            profile_id = int(cursor.lastrowid)
            self._replace_resume_profile_selections(
                connection,
                resume_profile_id=profile_id,
                selected_skill_ids=selected_skill_ids or [],
                selected_work_experience_ids=selected_work_experience_ids or [],
                selected_project_ids=selected_project_ids or [],
                selected_education_ids=selected_education_ids or [],
                selected_certification_ids=selected_certification_ids or [],
                selected_language_ids=selected_language_ids or [],
            )
            self._refresh_resume_profile_sections(
                connection,
                profile_id,
                fallback_content=content,
                section_instructions=section_instructions or {},
            )

        detail = self.get_resume_profile_detail(profile_id)
        assert detail is not None
        return detail

    def update_resume_profile(
        self,
        resume_profile_id: int,
        *,
        name: str,
        headline: str | None = None,
        summary: str | None = None,
        content: str | None = None,
        section_instructions: dict[str, str] | None = None,
        selected_skill_ids: list[int] | None = None,
        selected_work_experience_ids: list[int] | None = None,
        selected_project_ids: list[int] | None = None,
        selected_education_ids: list[int] | None = None,
        selected_certification_ids: list[int] | None = None,
        selected_language_ids: list[int] | None = None,
    ) -> ResumeProfileDetail | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM resume_profiles WHERE id = ?",
                (resume_profile_id,),
            ).fetchone()
            if existing is None:
                return None

            connection.execute(
                """
                UPDATE resume_profiles
                SET name = ?, headline = ?, summary = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, headline, summary, timestamp, resume_profile_id),
            )
            self._replace_resume_profile_selections(
                connection,
                resume_profile_id=resume_profile_id,
                selected_skill_ids=selected_skill_ids or [],
                selected_work_experience_ids=selected_work_experience_ids or [],
                selected_project_ids=selected_project_ids or [],
                selected_education_ids=selected_education_ids or [],
                selected_certification_ids=selected_certification_ids or [],
                selected_language_ids=selected_language_ids or [],
            )
            self._refresh_resume_profile_sections(
                connection,
                resume_profile_id,
                fallback_content=content,
                section_instructions=section_instructions or {},
            )

        return self.get_resume_profile_detail(resume_profile_id)

    def delete_resume_profile(self, resume_profile_id: int) -> bool:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM resume_profiles WHERE id = ?",
                (resume_profile_id,),
            ).fetchone()
            if existing is None:
                return False

            self._delete_resume_profile_selections(connection, resume_profile_id)
            connection.execute(
                "DELETE FROM resume_profile_sections WHERE resume_profile_id = ?",
                (resume_profile_id,),
            )
            connection.execute(
                "DELETE FROM compatibility_checks WHERE resume_profile_id = ?",
                (resume_profile_id,),
            )
            connection.execute(
                "DELETE FROM resume_profiles WHERE id = ?",
                (resume_profile_id,),
            )

        return True

    def list_resume_profiles(self) -> list[ResumeProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, headline, summary, content, created_at, updated_at
                FROM resume_profiles
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()

        return [self._row_to_resume_profile(row) for row in rows]

    def get_resume_profile(self, resume_profile_id: int) -> ResumeProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, headline, summary, content, created_at, updated_at
                FROM resume_profiles
                WHERE id = ?
                """,
                (resume_profile_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_resume_profile(row)

    def get_resume_profile_detail(self, resume_profile_id: int) -> ResumeProfileDetail | None:
        profile = self.get_resume_profile(resume_profile_id)
        if profile is None:
            return None

        with self._connect() as connection:
            return ResumeProfileDetail(
                **profile.model_dump(),
                selected_skill_ids=self._fetch_selected_ids(
                    connection, "resume_profile_selected_skills", "skill_id", resume_profile_id
                ),
                selected_work_experience_ids=self._fetch_selected_ids(
                    connection, "resume_profile_selected_work_experiences", "work_experience_id", resume_profile_id
                ),
                selected_project_ids=self._fetch_selected_ids(
                    connection, "resume_profile_selected_projects", "project_id", resume_profile_id
                ),
                selected_education_ids=self._fetch_selected_ids(
                    connection, "resume_profile_selected_education", "education_id", resume_profile_id
                ),
                selected_certification_ids=self._fetch_selected_ids(
                    connection, "resume_profile_selected_certifications", "certification_id", resume_profile_id
                ),
                selected_language_ids=self._fetch_selected_ids(
                    connection, "resume_profile_selected_languages", "language_id", resume_profile_id
                ),
                sections=self._list_resume_profile_sections(connection, resume_profile_id),
            )

    def get_resume_workspace(self) -> ResumeWorkspace:
        return ResumeWorkspace(
            candidate_profile=self.get_candidate_profile(),
            skills=self.list_master_skills(),
            work_experiences=self.list_master_work_experiences(),
            projects=self.list_master_projects(),
            education=self.list_master_education(),
            certifications=self.list_master_certifications(),
            languages=self.list_master_languages(),
            links=self.list_master_links(),
            resume_profiles=self.list_resume_profiles(),
        )

    def get_candidate_profile(self) -> CandidateProfile:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, summary, created_at, updated_at
                FROM candidate_profile
                WHERE id = 1
                """
            ).fetchone()
        return self._row_to_candidate_profile(row)

    def update_candidate_profile(self, payload: UpdateCandidateProfileRequest) -> CandidateProfile:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE candidate_profile
                SET summary = ?, updated_at = ?
                WHERE id = 1
                """,
                (payload.summary, timestamp),
            )
            row = connection.execute(
                """
                SELECT id, summary, created_at, updated_at
                FROM candidate_profile
                WHERE id = 1
                """
            ).fetchone()
        return self._row_to_candidate_profile(row)

    def get_openrouter_settings(self) -> OpenRouterSettings:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, api_key, provider, default_model, updated_at
                FROM opencode_settings
                WHERE id = 1
                """
            ).fetchone()

        saved_api_key = row["api_key"] if row else None
        env_api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENCODE_API_KEY")
            or os.environ.get("OPENCODE_AUTH_TOKEN")
        )
        effective_api_key = saved_api_key or env_api_key
        api_key_source = "saved" if saved_api_key else ("environment" if env_api_key else "none")
        saved_provider = row["provider"] if row else None
        effective_provider = saved_provider or os.environ.get("OPENROUTER_PROVIDER") or os.environ.get("OPENCODE_PROVIDER") or "openrouter"
        saved_default_model = row["default_model"] if row else None
        effective_default_model = saved_default_model or os.environ.get("OPENROUTER_MODEL") or os.environ.get("OPENCODE_MODEL")
        return OpenRouterSettings(
            has_api_key=bool(effective_api_key),
            masked_api_key=self._mask_secret(effective_api_key) if effective_api_key else None,
            api_key_source=api_key_source,
            saved_provider=saved_provider,
            effective_provider=effective_provider,
            saved_default_model=saved_default_model,
            effective_default_model=effective_default_model,
            updated_at=row["updated_at"] if row and (saved_api_key or saved_default_model) else None,
        )

    def update_openrouter_settings(self, payload: UpdateOpenRouterSettingsRequest) -> OpenRouterSettings:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT api_key, provider, default_model
                FROM opencode_settings
                WHERE id = 1
                """
            ).fetchone()
            current_api_key = current["api_key"] if current else None
            current_provider = current["provider"] if current else "openrouter"
            next_api_key = current_api_key
            if payload.api_key is not None:
                normalized_api_key = payload.api_key.strip()
                if normalized_api_key:
                    next_api_key = normalized_api_key
            next_provider = payload.provider.strip() if payload.provider else current_provider
            next_default_model = payload.default_model.strip() if payload.default_model else None
            self._validate_settings_model_id(
                connection,
                provider=next_provider,
                model_id=next_default_model,
            )
            connection.execute(
                """
                UPDATE opencode_settings
                SET api_key = ?, provider = ?, default_model = ?, updated_at = ?
                WHERE id = 1
                """,
                (next_api_key, next_provider, next_default_model, timestamp),
            )
        return self.get_openrouter_settings()

    def get_openrouter_runtime_config(self) -> tuple[str | None, str, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT api_key, provider, default_model
                FROM opencode_settings
                WHERE id = 1
                """
            ).fetchone()
        saved_api_key = row["api_key"] if row else None
        saved_provider = row["provider"] if row else None
        saved_model = row["default_model"] if row else None
        api_key = (
            saved_api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENCODE_API_KEY")
            or os.environ.get("OPENCODE_AUTH_TOKEN")
        )
        provider = saved_provider or os.environ.get("OPENROUTER_PROVIDER") or os.environ.get("OPENCODE_PROVIDER") or "openrouter"
        model = saved_model or os.environ.get("OPENROUTER_MODEL") or os.environ.get("OPENCODE_MODEL")
        return api_key, provider, model

    def get_prompt_settings(self) -> PromptSettings:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT summary_prompt, skills_prompt, experience_prompt, projects_prompt, updated_at
                FROM prompt_settings
                WHERE id = 1
                """
            ).fetchone()
        if row is None:
            return PromptSettings()
        return PromptSettings(
            summary_prompt=row["summary_prompt"],
            skills_prompt=row["skills_prompt"],
            experience_prompt=row["experience_prompt"],
            projects_prompt=row["projects_prompt"],
            updated_at=row["updated_at"],
        )

    def update_prompt_settings(self, payload: UpdatePromptSettingsRequest) -> PromptSettings:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE prompt_settings
                SET summary_prompt = ?, skills_prompt = ?, experience_prompt = ?, projects_prompt = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    payload.summary_prompt,
                    payload.skills_prompt,
                    payload.experience_prompt,
                    payload.projects_prompt,
                    timestamp,
                ),
            )
        return self.get_prompt_settings()

    def list_settings_models(self, provider: str | None = None) -> tuple[list[str], list[ProviderModelOption], str | None]:
        with self._connect() as connection:
            provider_rows = connection.execute(
                """
                SELECT DISTINCT provider
                FROM opencode_model_registry
                ORDER BY provider ASC
                """
            ).fetchall()
            selected_provider = provider or "openrouter"
            model_rows = connection.execute(
                """
                SELECT provider, model_id, label, source, is_free, last_refreshed_at
                FROM opencode_model_registry
                WHERE provider = ?
                ORDER BY is_free DESC, label ASC, model_id ASC
                """,
                (selected_provider,),
            ).fetchall()
        providers = [row["provider"] for row in provider_rows] or ["openrouter"]
        models = [self._row_to_provider_model_option(row) for row in model_rows]
        updated_at = models[0].last_refreshed_at if models else None
        return providers, models, updated_at

    def refresh_openrouter_model_registry(self) -> tuple[list[str], list[ProviderModelOption], str | None]:
        with self._connect() as connection:
            self._seed_openrouter_model_registry(connection)
        return self.list_settings_models(provider="openrouter")

    def _seed_openrouter_model_registry(self, connection: sqlite3.Connection) -> None:
        refreshed_at = _utc_now_iso()
        valid_seed_ids = {model.model_id for model in self._seed_model_registry if model.provider == "openrouter"}
        placeholders = ", ".join("?" for _ in valid_seed_ids) or "''"
        connection.execute(
            f"""
            DELETE FROM opencode_model_registry
            WHERE provider = 'openrouter' AND source = 'seed' AND model_id NOT IN ({placeholders})
            """,
            tuple(valid_seed_ids),
        )
        for model in self._seed_model_registry:
            connection.execute(
                """
                INSERT INTO opencode_model_registry (provider, model_id, label, source, is_free, last_refreshed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, model_id) DO UPDATE SET
                    label = excluded.label,
                    source = excluded.source,
                    is_free = excluded.is_free,
                    last_refreshed_at = excluded.last_refreshed_at
                """,
                (
                    model.provider,
                    model.model_id,
                    model.label,
                    model.source,
                    1 if model.is_free else 0,
                    refreshed_at,
                ),
            )

    @staticmethod
    def _looks_like_openrouter_model_id(model_id: str) -> bool:
        normalized = model_id.strip()
        if not normalized or " " in normalized:
            return False
        if normalized == "openrouter/auto":
            return True
        if normalized.startswith("openrouter/"):
            return False
        return "/" in normalized

    def _validate_settings_model_id(
        self,
        connection: sqlite3.Connection,
        *,
        provider: str,
        model_id: str | None,
    ) -> None:
        normalized_provider = provider.strip().lower() if provider else "openrouter"
        if normalized_provider != "openrouter" or not model_id:
            return
        normalized_model_id = model_id.strip()
        if not self._looks_like_openrouter_model_id(normalized_model_id):
            raise ValueError(
                "Invalid OpenRouter model id. Use the actual API model id, for example qwen/qwen3.6-plus:free."
            )
        if normalized_model_id == "openrouter/auto":
            return
        existing = connection.execute(
            """
            SELECT 1
            FROM opencode_model_registry
            WHERE provider = ? AND model_id = ?
            """,
            ("openrouter", normalized_model_id),
        ).fetchone()
        if existing is None:
            raise ValueError(
                f"Unknown OpenRouter model id: {normalized_model_id}. Refresh the registry or select a valid API model id."
            )

    def list_master_skills(self) -> list[MasterSkill]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, proficiency_level, notes, created_at, updated_at
                FROM master_skills
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_skill(row) for row in rows]

    def create_master_skill(self, payload: CreateMasterSkillRequest) -> MasterSkill:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_skills (name, proficiency_level, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.name, payload.proficiency_level, payload.notes, timestamp, timestamp),
            )
            row = connection.execute(
                """
                SELECT id, name, proficiency_level, notes, created_at, updated_at
                FROM master_skills
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_skill(row)

    def update_master_skill(self, skill_id: int, payload: UpdateMasterSkillRequest) -> MasterSkill | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_skills WHERE id = ?", (skill_id,)).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_skills
                SET name = ?, proficiency_level = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload.name, payload.proficiency_level, payload.notes, timestamp, skill_id),
            )
            updated_row = connection.execute(
                """
                SELECT id, name, proficiency_level, notes, created_at, updated_at
                FROM master_skills
                WHERE id = ?
                """,
                (skill_id,),
            ).fetchone()
        return self._row_to_master_skill(updated_row)

    def delete_master_skill(self, skill_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_skills WHERE id = ?", (skill_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM resume_profile_selected_skills WHERE skill_id = ?", (skill_id,))
            connection.execute("DELETE FROM master_skills WHERE id = ?", (skill_id,))
        return True

    def list_master_work_experiences(self) -> list[MasterWorkExperience]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, company, title, location, start_date, end_date, summary, highlights_json, created_at, updated_at
                FROM master_work_experiences
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_work_experience(row) for row in rows]

    def create_master_work_experience(self, payload: CreateMasterWorkExperienceRequest) -> MasterWorkExperience:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_work_experiences (
                    company, title, location, start_date, end_date, summary, highlights_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.company,
                    payload.title,
                    payload.location,
                    payload.start_date,
                    payload.end_date,
                    payload.summary,
                    json.dumps(payload.highlights),
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, company, title, location, start_date, end_date, summary, highlights_json, created_at, updated_at
                FROM master_work_experiences
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_work_experience(row)

    def update_master_work_experience(
        self,
        experience_id: int,
        payload: UpdateMasterWorkExperienceRequest,
    ) -> MasterWorkExperience | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM master_work_experiences WHERE id = ?",
                (experience_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_work_experiences
                SET company = ?, title = ?, location = ?, start_date = ?, end_date = ?, summary = ?, highlights_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.company,
                    payload.title,
                    payload.location,
                    payload.start_date,
                    payload.end_date,
                    payload.summary,
                    json.dumps(payload.highlights),
                    timestamp,
                    experience_id,
                ),
            )
            updated_row = connection.execute(
                """
                SELECT id, company, title, location, start_date, end_date, summary, highlights_json, created_at, updated_at
                FROM master_work_experiences
                WHERE id = ?
                """,
                (experience_id,),
            ).fetchone()
        return self._row_to_master_work_experience(updated_row)

    def delete_master_work_experience(self, experience_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM master_work_experiences WHERE id = ?",
                (experience_id,),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "DELETE FROM resume_profile_selected_work_experiences WHERE work_experience_id = ?",
                (experience_id,),
            )
            connection.execute("DELETE FROM master_work_experiences WHERE id = ?", (experience_id,))
        return True

    def list_master_projects(self) -> list[MasterProject]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, role, summary, technologies_json, url, created_at, updated_at
                FROM master_projects
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_project(row) for row in rows]

    def create_master_project(self, payload: CreateMasterProjectRequest) -> MasterProject:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_projects (name, role, summary, technologies_json, url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    payload.role,
                    payload.summary,
                    json.dumps(payload.technologies),
                    payload.url,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, name, role, summary, technologies_json, url, created_at, updated_at
                FROM master_projects
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_project(row)

    def update_master_project(self, project_id: int, payload: UpdateMasterProjectRequest) -> MasterProject | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_projects
                SET name = ?, role = ?, summary = ?, technologies_json = ?, url = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    payload.role,
                    payload.summary,
                    json.dumps(payload.technologies),
                    payload.url,
                    timestamp,
                    project_id,
                ),
            )
            updated_row = connection.execute(
                """
                SELECT id, name, role, summary, technologies_json, url, created_at, updated_at
                FROM master_projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        return self._row_to_master_project(updated_row)

    def delete_master_project(self, project_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM resume_profile_selected_projects WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM master_projects WHERE id = ?", (project_id,))
        return True

    def list_master_education(self) -> list[MasterEducation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, institution, degree, field_of_study, start_date, end_date, summary, created_at, updated_at
                FROM master_education
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_education(row) for row in rows]

    def create_master_education(self, payload: CreateMasterEducationRequest) -> MasterEducation:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_education (
                    institution, degree, field_of_study, start_date, end_date, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.institution,
                    payload.degree,
                    payload.field_of_study,
                    payload.start_date,
                    payload.end_date,
                    payload.summary,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, institution, degree, field_of_study, start_date, end_date, summary, created_at, updated_at
                FROM master_education
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_education(row)

    def update_master_education(self, education_id: int, payload: UpdateMasterEducationRequest) -> MasterEducation | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_education WHERE id = ?", (education_id,)).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_education
                SET institution = ?, degree = ?, field_of_study = ?, start_date = ?, end_date = ?, summary = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.institution,
                    payload.degree,
                    payload.field_of_study,
                    payload.start_date,
                    payload.end_date,
                    payload.summary,
                    timestamp,
                    education_id,
                ),
            )
            updated_row = connection.execute(
                """
                SELECT id, institution, degree, field_of_study, start_date, end_date, summary, created_at, updated_at
                FROM master_education
                WHERE id = ?
                """,
                (education_id,),
            ).fetchone()
        return self._row_to_master_education(updated_row)

    def delete_master_education(self, education_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_education WHERE id = ?", (education_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM resume_profile_selected_education WHERE education_id = ?", (education_id,))
            connection.execute("DELETE FROM master_education WHERE id = ?", (education_id,))
        return True

    def list_master_certifications(self) -> list[MasterCertification]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, issuer, issued_on, credential_id, credential_url, created_at, updated_at
                FROM master_certifications
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_certification(row) for row in rows]

    def create_master_certification(self, payload: CreateMasterCertificationRequest) -> MasterCertification:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_certifications (
                    name, issuer, issued_on, credential_id, credential_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    payload.issuer,
                    payload.issued_on,
                    payload.credential_id,
                    payload.credential_url,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, name, issuer, issued_on, credential_id, credential_url, created_at, updated_at
                FROM master_certifications
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_certification(row)

    def update_master_certification(
        self,
        certification_id: int,
        payload: UpdateMasterCertificationRequest,
    ) -> MasterCertification | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM master_certifications WHERE id = ?",
                (certification_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_certifications
                SET name = ?, issuer = ?, issued_on = ?, credential_id = ?, credential_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    payload.issuer,
                    payload.issued_on,
                    payload.credential_id,
                    payload.credential_url,
                    timestamp,
                    certification_id,
                ),
            )
            updated_row = connection.execute(
                """
                SELECT id, name, issuer, issued_on, credential_id, credential_url, created_at, updated_at
                FROM master_certifications
                WHERE id = ?
                """,
                (certification_id,),
            ).fetchone()
        return self._row_to_master_certification(updated_row)

    def delete_master_certification(self, certification_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM master_certifications WHERE id = ?",
                (certification_id,),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "DELETE FROM resume_profile_selected_certifications WHERE certification_id = ?",
                (certification_id,),
            )
            connection.execute("DELETE FROM master_certifications WHERE id = ?", (certification_id,))
        return True

    def list_master_languages(self) -> list[MasterLanguage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, proficiency, created_at, updated_at
                FROM master_languages
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_language(row) for row in rows]

    def create_master_language(self, payload: CreateMasterLanguageRequest) -> MasterLanguage:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_languages (name, proficiency, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (payload.name, payload.proficiency, timestamp, timestamp),
            )
            row = connection.execute(
                """
                SELECT id, name, proficiency, created_at, updated_at
                FROM master_languages
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_language(row)

    def update_master_language(self, language_id: int, payload: UpdateMasterLanguageRequest) -> MasterLanguage | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_languages WHERE id = ?", (language_id,)).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_languages
                SET name = ?, proficiency = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload.name, payload.proficiency, timestamp, language_id),
            )
            updated_row = connection.execute(
                """
                SELECT id, name, proficiency, created_at, updated_at
                FROM master_languages
                WHERE id = ?
                """,
                (language_id,),
            ).fetchone()
        return self._row_to_master_language(updated_row)

    def delete_master_language(self, language_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_languages WHERE id = ?", (language_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM resume_profile_selected_languages WHERE language_id = ?", (language_id,))
            connection.execute("DELETE FROM master_languages WHERE id = ?", (language_id,))
        return True

    def list_master_links(self) -> list[MasterLink]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, label, url, link_type, created_at, updated_at
                FROM master_links
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_master_link(row) for row in rows]

    def create_master_link(self, payload: CreateMasterLinkRequest) -> MasterLink:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO master_links (label, url, link_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payload.label, payload.url, payload.link_type, timestamp, timestamp),
            )
            row = connection.execute(
                """
                SELECT id, label, url, link_type, created_at, updated_at
                FROM master_links
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_master_link(row)

    def update_master_link(self, link_id: int, payload: UpdateMasterLinkRequest) -> MasterLink | None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_links WHERE id = ?", (link_id,)).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE master_links
                SET label = ?, url = ?, link_type = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload.label, payload.url, payload.link_type, timestamp, link_id),
            )
            updated_row = connection.execute(
                """
                SELECT id, label, url, link_type, created_at, updated_at
                FROM master_links
                WHERE id = ?
                """,
                (link_id,),
            ).fetchone()
        return self._row_to_master_link(updated_row)

    def delete_master_link(self, link_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM master_links WHERE id = ?", (link_id,)).fetchone()
            if row is None:
                return False
            connection.execute("DELETE FROM master_links WHERE id = ?", (link_id,))
        return True

    def _replace_resume_profile_selections(
        self,
        connection: sqlite3.Connection,
        *,
        resume_profile_id: int,
        selected_skill_ids: list[int],
        selected_work_experience_ids: list[int],
        selected_project_ids: list[int],
        selected_education_ids: list[int],
        selected_certification_ids: list[int],
        selected_language_ids: list[int],
    ) -> None:
        if len(selected_skill_ids) > 20:
            raise ValueError("A resume profile can include at most 20 skills.")

        self._replace_selection_rows(
            connection, "resume_profile_selected_skills", "skill_id", resume_profile_id, selected_skill_ids
        )
        self._replace_selection_rows(
            connection,
            "resume_profile_selected_work_experiences",
            "work_experience_id",
            resume_profile_id,
            selected_work_experience_ids,
        )
        self._replace_selection_rows(
            connection, "resume_profile_selected_projects", "project_id", resume_profile_id, selected_project_ids
        )
        self._replace_selection_rows(
            connection, "resume_profile_selected_education", "education_id", resume_profile_id, selected_education_ids
        )
        self._replace_selection_rows(
            connection,
            "resume_profile_selected_certifications",
            "certification_id",
            resume_profile_id,
            selected_certification_ids,
        )
        self._replace_selection_rows(
            connection, "resume_profile_selected_languages", "language_id", resume_profile_id, selected_language_ids
        )

    def _replace_selection_rows(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        item_column: str,
        resume_profile_id: int,
        item_ids: list[int],
    ) -> None:
        deduplicated_ids = list(dict.fromkeys(item_ids))
        connection.execute(
            f"DELETE FROM {table_name} WHERE resume_profile_id = ?",
            (resume_profile_id,),
        )
        for sort_order, item_id in enumerate(deduplicated_ids, start=1):
            connection.execute(
                f"""
                INSERT INTO {table_name} (resume_profile_id, {item_column}, sort_order)
                VALUES (?, ?, ?)
                """,
                (resume_profile_id, item_id, sort_order),
            )

    def _delete_resume_profile_selections(self, connection: sqlite3.Connection, resume_profile_id: int) -> None:
        connection.execute("DELETE FROM resume_profile_selected_skills WHERE resume_profile_id = ?", (resume_profile_id,))
        connection.execute(
            "DELETE FROM resume_profile_selected_work_experiences WHERE resume_profile_id = ?",
            (resume_profile_id,),
        )
        connection.execute("DELETE FROM resume_profile_selected_projects WHERE resume_profile_id = ?", (resume_profile_id,))
        connection.execute("DELETE FROM resume_profile_selected_education WHERE resume_profile_id = ?", (resume_profile_id,))
        connection.execute(
            "DELETE FROM resume_profile_selected_certifications WHERE resume_profile_id = ?",
            (resume_profile_id,),
        )
        connection.execute(
            "DELETE FROM resume_profile_selected_languages WHERE resume_profile_id = ?",
            (resume_profile_id,),
        )

    @staticmethod
    def _fetch_selected_ids(
        connection: sqlite3.Connection,
        table_name: str,
        item_column: str,
        resume_profile_id: int,
    ) -> list[int]:
        rows = connection.execute(
            f"""
            SELECT {item_column}
            FROM {table_name}
            WHERE resume_profile_id = ?
            ORDER BY sort_order ASC, {item_column} ASC
            """,
            (resume_profile_id,),
        ).fetchall()
        return [int(row[item_column]) for row in rows]

    def _refresh_resume_profile_sections(
        self,
        connection: sqlite3.Connection,
        resume_profile_id: int,
        *,
        fallback_content: str | None = None,
        section_instructions: dict[str, str],
    ) -> None:
        profile_row = connection.execute(
            """
            SELECT id, name, headline, summary, content, created_at, updated_at
            FROM resume_profiles
            WHERE id = ?
            """,
            (resume_profile_id,),
        ).fetchone()
        if profile_row is None:
            return

        detail = self._build_resume_profile_detail_from_row(connection, profile_row)
        existing_sections = {
            row["section_key"]: row
            for row in connection.execute(
                """
                SELECT section_key, custom_instructions, generated_content, generated_at
                FROM resume_profile_sections
                WHERE resume_profile_id = ?
                """,
                (resume_profile_id,),
            ).fetchall()
        }
        connection.execute(
            "DELETE FROM resume_profile_sections WHERE resume_profile_id = ?",
            (resume_profile_id,),
        )

        timestamp = _utc_now_iso()
        for section_key, label in self._resume_section_labels.items():
            existing_section = existing_sections.get(section_key)
            instruction = section_instructions.get(section_key)
            if instruction is None and existing_section is not None:
                instruction = existing_section["custom_instructions"]
            source_material = self._build_resume_profile_section_source(connection, detail, section_key)
            generated_content = existing_section["generated_content"] if existing_section is not None else None
            generated_at = existing_section["generated_at"] if existing_section is not None else None
            connection.execute(
                """
                INSERT INTO resume_profile_sections (
                    resume_profile_id,
                    section_key,
                    custom_instructions,
                    source_material,
                    generated_content,
                    updated_at,
                    generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resume_profile_id,
                    section_key,
                    instruction,
                    source_material,
                    generated_content,
                    timestamp,
                    generated_at,
                ),
            )

        sections = self._list_resume_profile_sections(connection, resume_profile_id)
        assembled_content = self._compose_resume_profile_content(detail, sections)
        final_content = assembled_content or (fallback_content or "")
        connection.execute(
            """
            UPDATE resume_profiles
            SET content = ?, updated_at = ?
            WHERE id = ?
            """,
            (final_content, _utc_now_iso(), resume_profile_id),
        )

    def _build_resume_profile_detail_from_row(
        self,
        connection: sqlite3.Connection,
        profile_row: sqlite3.Row,
    ) -> ResumeProfileDetail:
        resume_profile_id = int(profile_row["id"])
        return ResumeProfileDetail(
            **self._row_to_resume_profile(profile_row).model_dump(),
            selected_skill_ids=self._fetch_selected_ids(connection, "resume_profile_selected_skills", "skill_id", resume_profile_id),
            selected_work_experience_ids=self._fetch_selected_ids(
                connection,
                "resume_profile_selected_work_experiences",
                "work_experience_id",
                resume_profile_id,
            ),
            selected_project_ids=self._fetch_selected_ids(
                connection, "resume_profile_selected_projects", "project_id", resume_profile_id
            ),
            selected_education_ids=self._fetch_selected_ids(
                connection, "resume_profile_selected_education", "education_id", resume_profile_id
            ),
            selected_certification_ids=self._fetch_selected_ids(
                connection, "resume_profile_selected_certifications", "certification_id", resume_profile_id
            ),
            selected_language_ids=self._fetch_selected_ids(
                connection, "resume_profile_selected_languages", "language_id", resume_profile_id
            ),
            sections=[],
        )

    def _build_resume_profile_section_source(
        self,
        connection: sqlite3.Connection,
        profile: ResumeProfileDetail,
        section_key: str,
    ) -> str:
        builders = {
            "summary": self._build_summary_section_source,
            "skills": self._build_skills_section_source,
            "experience": self._build_experience_section_source,
            "projects": self._build_projects_section_source,
            "education": self._build_education_section_source,
            "certifications": self._build_certifications_section_source,
            "languages": self._build_languages_section_source,
        }
        builder = builders.get(section_key)
        if builder is None:
            return ""
        return builder(connection, profile).strip()

    def _compose_resume_profile_content(
        self,
        profile: ResumeProfileDetail,
        sections: list[ResumeProfileSection],
    ) -> str:
        populated_sections = []
        for section in sections:
            body = (section.generated_content or section.source_material).strip()
            if body:
                populated_sections.append((section.label, body))

        if not populated_sections and not profile.headline:
            return ""

        lines = [profile.name]
        if profile.headline:
            lines.append(profile.headline)
        for label, body in populated_sections:
            lines.extend(["", label, body])
        return "\n".join(lines).strip()

    def _list_resume_profile_sections(
        self,
        connection: sqlite3.Connection,
        resume_profile_id: int,
    ) -> list[ResumeProfileSection]:
        rows = connection.execute(
            """
            SELECT section_key, custom_instructions, source_material, generated_content, updated_at, generated_at
            FROM resume_profile_sections
            WHERE resume_profile_id = ?
            ORDER BY CASE section_key
                WHEN 'summary' THEN 1
                WHEN 'skills' THEN 2
                WHEN 'experience' THEN 3
                WHEN 'projects' THEN 4
                WHEN 'education' THEN 5
                WHEN 'certifications' THEN 6
                WHEN 'languages' THEN 7
                ELSE 99
            END
            """,
            (resume_profile_id,),
        ).fetchall()
        return [
            ResumeProfileSection(
                section_key=row["section_key"],
                label=self._resume_section_labels.get(row["section_key"], row["section_key"].title()),
                custom_instructions=row["custom_instructions"],
                source_material=row["source_material"],
                generated_content=row["generated_content"],
                updated_at=row["updated_at"],
                generated_at=row["generated_at"],
            )
            for row in rows
        ]

    def save_resume_profile_section_generation(
        self,
        *,
        resume_profile_id: int,
        section_key: str,
        generated_content: str,
    ) -> None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT resume_profile_id
                FROM resume_profile_sections
                WHERE resume_profile_id = ? AND section_key = ?
                """,
                (resume_profile_id, section_key),
            ).fetchone()
            if existing is None:
                raise ValueError("Resume profile section not found.")
            connection.execute(
                """
                UPDATE resume_profile_sections
                SET generated_content = ?, generated_at = ?, updated_at = ?
                WHERE resume_profile_id = ? AND section_key = ?
                """,
                (generated_content, timestamp, timestamp, resume_profile_id, section_key),
            )

            profile_row = connection.execute(
                """
                SELECT id, name, headline, summary, content, created_at, updated_at
                FROM resume_profiles
                WHERE id = ?
                """,
                (resume_profile_id,),
            ).fetchone()
            if profile_row is None:
                return
            detail = self._build_resume_profile_detail_from_row(connection, profile_row)
            sections = self._list_resume_profile_sections(connection, resume_profile_id)
            combined_content = self._compose_resume_profile_content(detail, sections)
            connection.execute(
                """
                UPDATE resume_profiles
                SET content = ?, updated_at = ?
                WHERE id = ?
                """,
                (combined_content or "", timestamp, resume_profile_id),
            )

    def _build_summary_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        lines = []
        candidate_profile = self.get_candidate_profile()
        if candidate_profile.summary:
            lines.append(f"Candidate profile summary: {candidate_profile.summary}")
        if profile.headline:
            lines.append(f"Positioning: {profile.headline}")
        if profile.summary:
            lines.append(f"Candidate guidance: {profile.summary}")

        experiences = self._selected_work_experiences(connection, profile.id)
        if experiences:
            lines.append("Relevant experience:")
            for experience in experiences:
                lines.append(f"- {experience.title} at {experience.company}")

        skills = self._selected_skills(connection, profile.id)
        if skills:
            lines.append(f"Core skills: {', '.join(skill.name for skill in skills)}")

        languages = self._selected_languages(connection, profile.id)
        if languages:
            lines.append(
                f"Languages: {', '.join(f'{language.name} ({language.proficiency})' for language in languages)}"
            )
        return "\n".join(lines)

    def _build_skills_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        skills = self._selected_skills(connection, profile.id)
        return "\n".join(
            f"- {skill.name}{f' ({skill.proficiency_level})' if skill.proficiency_level else ''}{f': {skill.notes}' if skill.notes else ''}"
            for skill in skills
        )

    def _build_experience_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        experiences = self._selected_work_experiences(connection, profile.id)
        lines: list[str] = []
        for experience in experiences:
            lines.append(f"{experience.title} | {experience.company}")
            meta = [part for part in [experience.location, self._format_date_range(experience.start_date, experience.end_date)] if part]
            if meta:
                lines.append(" | ".join(meta))
            if experience.summary:
                lines.append(f"Context: {experience.summary}")
            for highlight in experience.highlights:
                lines.append(f"- {highlight}")
            lines.append("")
        return "\n".join(lines).strip()

    def _build_projects_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        projects = self._selected_projects(connection, profile.id)
        lines: list[str] = []
        for project in projects:
            lines.append(project.name)
            meta = [part for part in [project.role, project.url] if part]
            if meta:
                lines.append(" | ".join(meta))
            if project.summary:
                lines.append(project.summary)
            if project.technologies:
                lines.append(f"Technologies: {', '.join(project.technologies)}")
            lines.append("")
        return "\n".join(lines).strip()

    def _build_education_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        education_items = self._selected_education(connection, profile.id)
        lines: list[str] = []
        for entry in education_items:
            title = entry.degree
            if entry.field_of_study:
                title = f"{title}, {entry.field_of_study}"
            lines.append(f"{title} | {entry.institution}")
            date_range = self._format_date_range(entry.start_date, entry.end_date)
            if date_range:
                lines.append(date_range)
            if entry.summary:
                lines.append(entry.summary)
            lines.append("")
        return "\n".join(lines).strip()

    def _build_certifications_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        certifications = self._selected_certifications(connection, profile.id)
        lines: list[str] = []
        for certification in certifications:
            lines.append(f"{certification.name} | {certification.issuer}")
            meta = [
                part
                for part in [certification.issued_on, certification.credential_id, certification.credential_url]
                if part
            ]
            if meta:
                lines.append(" | ".join(meta))
            lines.append("")
        return "\n".join(lines).strip()

    def _build_languages_section_source(self, connection: sqlite3.Connection, profile: ResumeProfileDetail) -> str:
        languages = self._selected_languages(connection, profile.id)
        return "\n".join(f"- {language.name} ({language.proficiency})" for language in languages)

    @staticmethod
    def _fetch_selected_items(
        connection: sqlite3.Connection,
        query: str,
        resume_profile_id: int,
        row_converter,
    ) -> list:
        rows = connection.execute(query, (resume_profile_id,)).fetchall()
        return [row_converter(row) for row in rows]

    def _selected_skills(self, connection: sqlite3.Connection, resume_profile_id: int) -> list[MasterSkill]:
        return self._fetch_selected_items(
            connection,
            """
            SELECT master_skills.id, master_skills.name, master_skills.proficiency_level, master_skills.notes, master_skills.created_at, master_skills.updated_at
            FROM resume_profile_selected_skills
            JOIN master_skills ON master_skills.id = resume_profile_selected_skills.skill_id
            WHERE resume_profile_selected_skills.resume_profile_id = ?
            ORDER BY resume_profile_selected_skills.sort_order ASC
            """,
            resume_profile_id,
            self._row_to_master_skill,
        )

    def _selected_work_experiences(
        self,
        connection: sqlite3.Connection,
        resume_profile_id: int,
    ) -> list[MasterWorkExperience]:
        return self._fetch_selected_items(
            connection,
            """
            SELECT master_work_experiences.id, master_work_experiences.company, master_work_experiences.title, master_work_experiences.location,
                   master_work_experiences.start_date, master_work_experiences.end_date, master_work_experiences.summary,
                   master_work_experiences.highlights_json, master_work_experiences.created_at, master_work_experiences.updated_at
            FROM resume_profile_selected_work_experiences
            JOIN master_work_experiences ON master_work_experiences.id = resume_profile_selected_work_experiences.work_experience_id
            WHERE resume_profile_selected_work_experiences.resume_profile_id = ?
            ORDER BY resume_profile_selected_work_experiences.sort_order ASC
            """,
            resume_profile_id,
            self._row_to_master_work_experience,
        )

    def _selected_projects(self, connection: sqlite3.Connection, resume_profile_id: int) -> list[MasterProject]:
        return self._fetch_selected_items(
            connection,
            """
            SELECT master_projects.id, master_projects.name, master_projects.role, master_projects.summary,
                   master_projects.technologies_json, master_projects.url, master_projects.created_at, master_projects.updated_at
            FROM resume_profile_selected_projects
            JOIN master_projects ON master_projects.id = resume_profile_selected_projects.project_id
            WHERE resume_profile_selected_projects.resume_profile_id = ?
            ORDER BY resume_profile_selected_projects.sort_order ASC
            """,
            resume_profile_id,
            self._row_to_master_project,
        )

    def _selected_education(self, connection: sqlite3.Connection, resume_profile_id: int) -> list[MasterEducation]:
        return self._fetch_selected_items(
            connection,
            """
            SELECT master_education.id, master_education.institution, master_education.degree, master_education.field_of_study,
                   master_education.start_date, master_education.end_date, master_education.summary, master_education.created_at, master_education.updated_at
            FROM resume_profile_selected_education
            JOIN master_education ON master_education.id = resume_profile_selected_education.education_id
            WHERE resume_profile_selected_education.resume_profile_id = ?
            ORDER BY resume_profile_selected_education.sort_order ASC
            """,
            resume_profile_id,
            self._row_to_master_education,
        )

    def _selected_certifications(
        self,
        connection: sqlite3.Connection,
        resume_profile_id: int,
    ) -> list[MasterCertification]:
        return self._fetch_selected_items(
            connection,
            """
            SELECT master_certifications.id, master_certifications.name, master_certifications.issuer, master_certifications.issued_on,
                   master_certifications.credential_id, master_certifications.credential_url, master_certifications.created_at, master_certifications.updated_at
            FROM resume_profile_selected_certifications
            JOIN master_certifications ON master_certifications.id = resume_profile_selected_certifications.certification_id
            WHERE resume_profile_selected_certifications.resume_profile_id = ?
            ORDER BY resume_profile_selected_certifications.sort_order ASC
            """,
            resume_profile_id,
            self._row_to_master_certification,
        )

    def _selected_languages(self, connection: sqlite3.Connection, resume_profile_id: int) -> list[MasterLanguage]:
        return self._fetch_selected_items(
            connection,
            """
            SELECT master_languages.id, master_languages.name, master_languages.proficiency, master_languages.created_at, master_languages.updated_at
            FROM resume_profile_selected_languages
            JOIN master_languages ON master_languages.id = resume_profile_selected_languages.language_id
            WHERE resume_profile_selected_languages.resume_profile_id = ?
            ORDER BY resume_profile_selected_languages.sort_order ASC
            """,
            resume_profile_id,
            self._row_to_master_language,
        )

    @staticmethod
    def _format_date_range(start_date: str | None, end_date: str | None) -> str | None:
        if start_date and end_date:
            return f"{start_date} - {end_date}"
        return start_date or end_date

    @staticmethod
    def _mask_secret(value: str) -> str:
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}{'*' * max(4, len(value) - 8)}{value[-4:]}"

    def save_compatibility_check(
        self,
        *,
        job_id: int,
        snapshot_id: int,
        resume_profile_id: int,
        score: int,
        decision: str,
        summary: str,
        strengths: list[str],
        gaps: list[str],
        raw_model_response: str,
    ) -> CompatibilityCheckResult:
        timestamp = _utc_now_iso()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO compatibility_checks (
                    job_id,
                    snapshot_id,
                    resume_profile_id,
                    score,
                    decision,
                    summary,
                    strengths_json,
                    gaps_json,
                    raw_model_response,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    snapshot_id,
                    resume_profile_id,
                    score,
                    decision,
                    summary,
                    json.dumps(strengths),
                    json.dumps(gaps),
                    raw_model_response,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    resume_profile_id,
                    score,
                    decision,
                    summary,
                    strengths_json,
                    gaps_json,
                    raw_model_response,
                    created_at
                FROM compatibility_checks
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()

        return self._row_to_compatibility_check(row)

    def save_candidate_compatibility_check(
        self,
        *,
        job_id: int,
        snapshot_id: int,
        score: int,
        short_reason: str,
        strengths: list[str],
        gaps: list[str],
        raw_model_response: str,
    ) -> CandidateCompatibilityCheckResult:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO candidate_compatibility_checks (
                    job_id,
                    snapshot_id,
                    score,
                    short_reason,
                    strengths_json,
                    gaps_json,
                    raw_model_response,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    snapshot_id,
                    score,
                    short_reason,
                    json.dumps(strengths),
                    json.dumps(gaps),
                    raw_model_response,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    score,
                    short_reason,
                    strengths_json,
                    gaps_json,
                    raw_model_response,
                    created_at
                FROM candidate_compatibility_checks
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
        return self._row_to_candidate_compatibility_check(row)

    def create_job_check_batch(self, *, mode: str, job_ids: list[int]) -> JobCheckBatchRun:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_check_batches (
                    mode,
                    status,
                    total_jobs,
                    completed_jobs,
                    failed_jobs,
                    last_error,
                    created_at,
                    updated_at
                ) VALUES (?, 'running', ?, 0, 0, NULL, ?, ?)
                """,
                (mode, len(job_ids), timestamp, timestamp),
            )
            batch_id = int(cursor.lastrowid)
            for job_id in job_ids:
                connection.execute(
                    """
                    INSERT INTO job_check_batch_items (
                        batch_id,
                        job_id,
                        status,
                        error_message,
                        updated_at
                    ) VALUES (?, ?, 'pending', NULL, ?)
                    """,
                    (batch_id, job_id, timestamp),
                )
        return self.get_job_check_batch(batch_id)

    def get_job_check_batch(self, batch_id: int) -> JobCheckBatchRun | None:
        with self._connect() as connection:
            batch_row = connection.execute(
                """
                SELECT
                    id,
                    mode,
                    status,
                    total_jobs,
                    completed_jobs,
                    failed_jobs,
                    created_at,
                    updated_at,
                    last_error
                FROM job_check_batches
                WHERE id = ?
                """,
                (batch_id,),
            ).fetchone()
            if batch_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT
                    id,
                    batch_id,
                    job_id,
                    status,
                    error_message,
                    updated_at
                FROM job_check_batch_items
                WHERE batch_id = ?
                ORDER BY id ASC
                """,
                (batch_id,),
            ).fetchall()
        return self._row_to_job_check_batch(batch_row, item_rows)

    def get_current_or_latest_job_check_batch(self) -> JobCheckBatchRun | None:
        with self._connect() as connection:
            batch_row = connection.execute(
                """
                SELECT
                    id,
                    mode,
                    status,
                    total_jobs,
                    completed_jobs,
                    failed_jobs,
                    created_at,
                    updated_at,
                    last_error
                FROM job_check_batches
                ORDER BY
                    CASE WHEN status = 'running' THEN 0 ELSE 1 END,
                    updated_at DESC,
                    id DESC
                LIMIT 1
                """
            ).fetchone()
            if batch_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT
                    id,
                    batch_id,
                    job_id,
                    status,
                    error_message,
                    updated_at
                FROM job_check_batch_items
                WHERE batch_id = ?
                ORDER BY id ASC
                """,
                (batch_row["id"],),
            ).fetchall()
        return self._row_to_job_check_batch(batch_row, item_rows)

    def update_job_check_batch_item(
        self,
        *,
        batch_id: int,
        job_id: int,
        status_value: str,
        error_message: str | None = None,
    ) -> None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE job_check_batch_items
                SET status = ?, error_message = ?, updated_at = ?
                WHERE batch_id = ? AND job_id = ?
                """,
                (status_value, error_message, timestamp, batch_id, job_id),
            )
            self._refresh_job_check_batch_counts(connection, batch_id, timestamp)

    def complete_job_check_batch(self, *, batch_id: int, status_value: str, last_error: str | None = None) -> None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE job_check_batches
                SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status_value, last_error, timestamp, batch_id),
            )
            self._refresh_job_check_batch_counts(connection, batch_id, timestamp)

    @staticmethod
    def _refresh_job_check_batch_counts(connection: sqlite3.Connection, batch_id: int, timestamp: str) -> None:
        counts = connection.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_jobs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_jobs
            FROM job_check_batch_items
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE job_check_batches
            SET completed_jobs = ?, failed_jobs = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                int(counts["completed_jobs"] or 0),
                int(counts["failed_jobs"] or 0),
                timestamp,
                batch_id,
            ),
        )

    def get_latest_snapshot_for_job(self, job_id: int) -> LatestJobSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    title,
                    company,
                    location,
                    visible_text,
                    html,
                    plugin_name,
                    captured_at
                FROM job_snapshots
                WHERE job_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_latest_snapshot(row)

    def delete_job(self, job_id: int) -> bool:
        with self._connect() as connection:
            existing_job = connection.execute(
                "SELECT id FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if existing_job is None:
                return False

            connection.execute(
                "DELETE FROM compatibility_checks WHERE job_id = ?",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM candidate_compatibility_checks WHERE job_id = ?",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM job_snapshots WHERE job_id = ?",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM jobs WHERE id = ?",
                (job_id,),
            )

        return True

    @staticmethod
    def _find_existing_job_id(
        connection: sqlite3.Connection,
        *,
        source: str,
        external_job_id: str | None,
        source_url: str,
        title: str | None,
        company: str | None,
    ) -> int | None:
        if external_job_id:
            row = connection.execute(
                """
                SELECT id
                FROM jobs
                WHERE source = ? AND external_job_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source, external_job_id),
            ).fetchone()
            if row is not None:
                return int(row["id"])

        fallback_title = title or ""
        fallback_company = company or ""
        row = connection.execute(
            """
            SELECT jobs.id
            FROM jobs
            LEFT JOIN job_snapshots ON job_snapshots.job_id = jobs.id
            WHERE jobs.source_url = ?
              AND COALESCE(job_snapshots.title, jobs.page_title, jobs.tentative_job_title, '') = ?
              AND COALESCE(job_snapshots.company, '') = ?
            ORDER BY jobs.id DESC, job_snapshots.id DESC
            LIMIT 1
            """,
            (source_url, fallback_title, fallback_company),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def _get_job_row(self, job_id: int) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT
                    id,
                    source,
                    external_job_id,
                    source_url,
                    page_title,
                    tentative_job_title,
                    status,
                    created_at
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()

    @staticmethod
    def _row_to_stored_job(row: sqlite3.Row) -> StoredJob:
        return StoredJob(
            id=row["id"],
            source=row["source"],
            external_job_id=row["external_job_id"],
            source_url=row["source_url"],
            page_title=row["page_title"],
            tentative_job_title=row["tentative_job_title"],
            status=row["status"],
            created_at=row["created_at"],
        )

    @classmethod
    def _row_to_job_list_item(cls, row: sqlite3.Row) -> JobListItem:
        latest_snapshot = None
        if row["latest_snapshot_id"] is not None:
            latest_snapshot = LatestJobSnapshot(
                id=row["latest_snapshot_id"],
                title=row["latest_snapshot_title"],
                company=row["latest_snapshot_company"],
                location=row["latest_snapshot_location"],
                visible_text=row["latest_snapshot_visible_text"],
                html=row["latest_snapshot_html"],
                plugin_name=row["latest_snapshot_plugin_name"],
                captured_at=row["latest_snapshot_captured_at"],
            )
        latest_candidate_check = None
        if row["latest_candidate_check_id"] is not None:
            latest_candidate_check = CandidateCompatibilityCheckResult(
                id=row["latest_candidate_check_id"],
                score=row["latest_candidate_check_score"],
                short_reason=row["latest_candidate_check_short_reason"],
                strengths=json.loads(row["latest_candidate_check_strengths_json"]),
                gaps=json.loads(row["latest_candidate_check_gaps_json"]),
                raw_model_response=row["latest_candidate_check_raw_model_response"],
                created_at=row["latest_candidate_check_created_at"],
            )

        return JobListItem(
            **cls._row_to_stored_job(row).model_dump(),
            latest_snapshot=latest_snapshot,
            latest_candidate_compatibility_check=latest_candidate_check,
        )

    @staticmethod
    def _row_to_latest_snapshot(row: sqlite3.Row) -> LatestJobSnapshot:
        return LatestJobSnapshot(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            visible_text=row["visible_text"],
            html=row["html"],
            plugin_name=row["plugin_name"],
            captured_at=row["captured_at"],
        )

    @staticmethod
    def _row_to_resume_profile(row: sqlite3.Row) -> ResumeProfile:
        return ResumeProfile(
            id=row["id"],
            name=row["name"],
            headline=row["headline"],
            summary=row["summary"],
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_skill(row: sqlite3.Row) -> MasterSkill:
        return MasterSkill(
            id=row["id"],
            name=row["name"],
            proficiency_level=row["proficiency_level"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_work_experience(row: sqlite3.Row) -> MasterWorkExperience:
        return MasterWorkExperience(
            id=row["id"],
            company=row["company"],
            title=row["title"],
            location=row["location"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            summary=row["summary"],
            highlights=json.loads(row["highlights_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_project(row: sqlite3.Row) -> MasterProject:
        return MasterProject(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            summary=row["summary"],
            technologies=json.loads(row["technologies_json"]),
            url=row["url"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_education(row: sqlite3.Row) -> MasterEducation:
        return MasterEducation(
            id=row["id"],
            institution=row["institution"],
            degree=row["degree"],
            field_of_study=row["field_of_study"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_certification(row: sqlite3.Row) -> MasterCertification:
        return MasterCertification(
            id=row["id"],
            name=row["name"],
            issuer=row["issuer"],
            issued_on=row["issued_on"],
            credential_id=row["credential_id"],
            credential_url=row["credential_url"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_language(row: sqlite3.Row) -> MasterLanguage:
        return MasterLanguage(
            id=row["id"],
            name=row["name"],
            proficiency=row["proficiency"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_master_link(row: sqlite3.Row) -> MasterLink:
        return MasterLink(
            id=row["id"],
            label=row["label"],
            url=row["url"],
            link_type=row["link_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_candidate_profile(row: sqlite3.Row) -> CandidateProfile:
        return CandidateProfile(
            id=row["id"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_provider_model_option(row: sqlite3.Row) -> ProviderModelOption:
        return ProviderModelOption(
            provider=row["provider"],
            model_id=row["model_id"],
            label=row["label"],
            source=row["source"],
            is_free=bool(row["is_free"]),
            last_refreshed_at=row["last_refreshed_at"],
        )

    @staticmethod
    def _row_to_compatibility_check(row: sqlite3.Row) -> CompatibilityCheckResult:
        return CompatibilityCheckResult(
            id=row["id"],
            resume_profile_id=row["resume_profile_id"],
            score=row["score"],
            decision=row["decision"],
            summary=row["summary"],
            strengths=json.loads(row["strengths_json"]),
            gaps=json.loads(row["gaps_json"]),
            raw_model_response=row["raw_model_response"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_candidate_compatibility_check(row: sqlite3.Row) -> CandidateCompatibilityCheckResult:
        return CandidateCompatibilityCheckResult(
            id=row["id"],
            score=row["score"],
            short_reason=row["short_reason"],
            strengths=json.loads(row["strengths_json"]),
            gaps=json.loads(row["gaps_json"]),
            raw_model_response=row["raw_model_response"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_job_check_batch_item(row: sqlite3.Row) -> JobCheckBatchItem:
        return JobCheckBatchItem(
            id=row["id"],
            batch_id=row["batch_id"],
            job_id=row["job_id"],
            status=row["status"],
            error_message=row["error_message"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def _row_to_job_check_batch(cls, batch_row: sqlite3.Row, item_rows: list[sqlite3.Row]) -> JobCheckBatchRun:
        return JobCheckBatchRun(
            id=batch_row["id"],
            mode=batch_row["mode"],
            status=batch_row["status"],
            total_jobs=batch_row["total_jobs"],
            completed_jobs=batch_row["completed_jobs"],
            failed_jobs=batch_row["failed_jobs"],
            created_at=batch_row["created_at"],
            updated_at=batch_row["updated_at"],
            last_error=batch_row["last_error"],
            items=[cls._row_to_job_check_batch_item(row) for row in item_rows],
        )


def get_job_store() -> SQLiteJobStore:
    return SQLiteJobStore()
