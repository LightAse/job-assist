import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.jobs import (
    CompatibilityCheckResult,
    JobDetail,
    LatestJobSnapshot,
    ResumeProfile,
    StoredJob,
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
    snapshot_id: int


class SQLiteJobStore:
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
                    created_at TEXT NOT NULL
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
                """
            )
            self._ensure_column(connection, "job_snapshots", "company", "TEXT")
            self._ensure_column(connection, "job_snapshots", "location", "TEXT")

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
        timestamp = _utc_now_iso()

        with self._connect() as connection:
            job_cursor = connection.execute(
                """
                INSERT INTO jobs (
                    source,
                    external_job_id,
                    source_url,
                    page_title,
                    tentative_job_title,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    structured_data.get("source"),
                    structured_data.get("external_job_id"),
                    str(scrape_result.source_url),
                    structured_data.get("page_title"),
                    structured_data.get("tentative_job_title"),
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
        )

    def list_jobs(self) -> list[StoredJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    source,
                    external_job_id,
                    source_url,
                    page_title,
                    tentative_job_title,
                    created_at
                FROM jobs
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        return [self._row_to_stored_job(row) for row in rows]

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

        return JobDetail(
            **self._row_to_stored_job(job_row).model_dump(),
            latest_snapshot=self._row_to_latest_snapshot(snapshot_row) if snapshot_row else None,
            latest_compatibility_check=self._row_to_compatibility_check(compatibility_row) if compatibility_row else None,
        )

    def create_resume_profile(self, *, name: str, content: str) -> ResumeProfile:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO resume_profiles (name, content, created_at)
                VALUES (?, ?, ?)
                """,
                (name, content, timestamp),
            )
            row = connection.execute(
                """
                SELECT id, name, content, created_at
                FROM resume_profiles
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()

        return self._row_to_resume_profile(row)

    def list_resume_profiles(self) -> list[ResumeProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, content, created_at
                FROM resume_profiles
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        return [self._row_to_resume_profile(row) for row in rows]

    def get_resume_profile(self, resume_profile_id: int) -> ResumeProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, content, created_at
                FROM resume_profiles
                WHERE id = ?
                """,
                (resume_profile_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_resume_profile(row)

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
                "DELETE FROM job_snapshots WHERE job_id = ?",
                (job_id,),
            )
            connection.execute(
                "DELETE FROM jobs WHERE id = ?",
                (job_id,),
            )

        return True

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
            created_at=row["created_at"],
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
            content=row["content"],
            created_at=row["created_at"],
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


def get_job_store() -> SQLiteJobStore:
    return SQLiteJobStore()
