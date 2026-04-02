import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.jobs import StoredJob
from app.schemas.scrape import ScrapeContext, ScrapeCurrentResponse


def _default_database_path() -> Path:
    configured_path = os.environ.get("JOB_ASSIST_DB_PATH")
    if configured_path:
        return Path(configured_path)
    return Path("data/job_assist.db")


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
                    html TEXT,
                    visible_text TEXT,
                    plugin_name TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs (id)
                );
                """
            )

    def save_matched_scrape(
        self,
        context: ScrapeContext,
        scrape_result: ScrapeCurrentResponse,
    ) -> PersistedScrapeRecord:
        structured_data = scrape_result.structured_data
        timestamp = datetime.now(timezone.utc).isoformat()

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
                    html,
                    visible_text,
                    plugin_name,
                    captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(context.url),
                    context.title,
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
        with self._connect() as connection:
            row = connection.execute(
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

        if row is None:
            return None
        return self._row_to_stored_job(row)

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


def get_job_store() -> SQLiteJobStore:
    return SQLiteJobStore()
