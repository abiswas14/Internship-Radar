from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from swe_job_radar.identity import canonicalize_url, job_fingerprint
from swe_job_radar.models import Classification, ClassificationResult, Job


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True, slots=True)
class ObservationResult:
    new_jobs: list[Job]
    baseline_created: bool
    reactivated_without_alert: int = 0


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    fingerprint TEXT PRIMARY KEY,
                    company TEXT NOT NULL,
                    external_id TEXT,
                    title TEXT NOT NULL,
                    location TEXT,
                    description TEXT,
                    job_url TEXT NOT NULL,
                    apply_url TEXT,
                    source_url TEXT NOT NULL,
                    employment_type TEXT,
                    date_posted TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    inactive_since_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    classification TEXT,
                    classification_reason TEXT,
                    classification_confidence REAL,
                    notification_sent_at TEXT,
                    notification_attempts INTEGER NOT NULL DEFAULT 0,
                    next_notification_attempt_at TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_company_active ON jobs(company, active);
                CREATE UNIQUE INDEX IF NOT EXISTS jobs_company_external_id
                    ON jobs(company, external_id) WHERE external_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS scraper_state (
                    company TEXT PRIMARY KEY,
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    first_failure_at TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_job_count INTEGER,
                    previous_normal_job_count INTEGER,
                    last_error TEXT,
                    operational_alert_sent_at TEXT
                );

                CREATE TABLE IF NOT EXISTS company_baselines (
                    company TEXT PRIMARY KEY,
                    completed_at TEXT NOT NULL,
                    job_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL REFERENCES jobs(fingerprint),
                    idempotency_key TEXT NOT NULL UNIQUE,
                    attempted_at TEXT NOT NULL,
                    succeeded INTEGER NOT NULL,
                    error TEXT
                );
                """
            )
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (1, ?)",
                (_iso(datetime.now(UTC)),),
            )

    def has_baseline(self, company: str) -> bool:
        with self.connect() as db:
            return (
                db.execute(
                    "SELECT 1 FROM company_baselines WHERE company = ?", (company,)
                ).fetchone()
                is not None
            )

    def observe_jobs(
        self,
        company: str,
        jobs: Sequence[Job],
        *,
        observed_at: datetime | None = None,
        force_baseline: bool = False,
        repost_after_days: int = 30,
        mark_missing: bool = True,
    ) -> ObservationResult:
        now = observed_at or datetime.now(UTC)
        now_s = _iso(now)
        fingerprints = {job_fingerprint(job): job for job in jobs}
        new_jobs: list[Job] = []
        reactivated_without_alert = 0

        with self.connect() as db:
            has_baseline = (
                db.execute(
                    "SELECT 1 FROM company_baselines WHERE company = ?", (company,)
                ).fetchone()
                is not None
            )
            is_baseline = force_baseline or not has_baseline

            for fingerprint, job in fingerprints.items():
                row = db.execute(
                    "SELECT active, inactive_since_at FROM jobs WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if row is None:
                    db.execute(
                        """
                        INSERT INTO jobs (
                            fingerprint, company, external_id, title, location, description,
                            job_url, apply_url, source_url, employment_type, date_posted,
                            first_seen_at, last_seen_at, active
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            fingerprint,
                            job.company,
                            job.external_id,
                            job.title,
                            job.location,
                            job.description,
                            canonicalize_url(job.job_url),
                            canonicalize_url(job.apply_url) if job.apply_url else None,
                            canonicalize_url(job.source_url),
                            job.employment_type,
                            _iso(job.date_posted),
                            now_s,
                            now_s,
                        ),
                    )
                    if not is_baseline:
                        new_jobs.append(job)
                    continue

                was_active = bool(row["active"])
                inactive_since = _dt(row["inactive_since_at"])
                is_repost = (
                    not was_active
                    and inactive_since is not None
                    and now - inactive_since >= timedelta(days=repost_after_days)
                )
                db.execute(
                    """
                    UPDATE jobs SET title=?, location=?, description=?, job_url=?, apply_url=?,
                        source_url=?, employment_type=?, date_posted=?, last_seen_at=?, active=1,
                        inactive_since_at=NULL
                    WHERE fingerprint=?
                    """,
                    (
                        job.title,
                        job.location,
                        job.description,
                        canonicalize_url(job.job_url),
                        canonicalize_url(job.apply_url) if job.apply_url else None,
                        canonicalize_url(job.source_url),
                        job.employment_type,
                        _iso(job.date_posted),
                        now_s,
                        fingerprint,
                    ),
                )
                if not was_active:
                    if is_repost and not is_baseline:
                        db.execute(
                            """UPDATE jobs SET classification=NULL, classification_reason=NULL,
                            classification_confidence=NULL, notification_sent_at=NULL,
                            notification_attempts=0, next_notification_attempt_at=NULL
                            WHERE fingerprint=?""",
                            (fingerprint,),
                        )
                        new_jobs.append(job)
                    else:
                        reactivated_without_alert += 1

            if mark_missing:
                if fingerprints:
                    placeholders = ",".join("?" for _ in fingerprints)
                    db.execute(
                        f"""UPDATE jobs SET active=0,
                        inactive_since_at=COALESCE(inactive_since_at, ?)
                        WHERE company=? AND active=1 AND fingerprint NOT IN ({placeholders})""",
                        (now_s, company, *fingerprints),
                    )
                else:
                    db.execute(
                        """UPDATE jobs SET active=0,
                        inactive_since_at=COALESCE(inactive_since_at, ?)
                        WHERE company=? AND active=1""",
                        (now_s, company),
                    )

            if is_baseline:
                db.execute(
                    """INSERT INTO company_baselines(company, completed_at, job_count)
                    VALUES (?, ?, ?) ON CONFLICT(company) DO UPDATE SET
                    completed_at=excluded.completed_at, job_count=excluded.job_count""",
                    (company, now_s, len(fingerprints)),
                )

        return ObservationResult(new_jobs, is_baseline, reactivated_without_alert)

    def set_classification(self, job: Job, result: ClassificationResult) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE jobs SET classification=?, classification_reason=?,
                classification_confidence=? WHERE fingerprint=?""",
                (
                    result.classification.value,
                    result.reason,
                    result.confidence,
                    job_fingerprint(job),
                ),
            )

    def pending_notifications(self, *, now: datetime | None = None) -> list[sqlite3.Row]:
        now_s = _iso(now or datetime.now(UTC))
        with self.connect() as db:
            return list(
                db.execute(
                    """
                    SELECT * FROM jobs
                    WHERE notification_sent_at IS NULL
                      AND classification IN (?, ?, ?)
                      AND (next_notification_attempt_at IS NULL
                           OR next_notification_attempt_at <= ?)
                    ORDER BY first_seen_at
                    """,
                    (
                        Classification.INTERN_2027.value,
                        Classification.NEW_GRAD_2027.value,
                        Classification.RELEVANT_BUT_AMBIGUOUS.value,
                        now_s,
                    ),
                )
            )

    def record_notification(
        self,
        fingerprint: str,
        idempotency_key: str,
        *,
        succeeded: bool,
        error: str | None = None,
        attempted_at: datetime | None = None,
    ) -> None:
        now = attempted_at or datetime.now(UTC)
        with self.connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO notification_attempts(
                    fingerprint, idempotency_key, attempted_at, succeeded, error
                ) VALUES (?, ?, ?, ?, ?)""",
                (fingerprint, idempotency_key, _iso(now), int(succeeded), error),
            )
            if succeeded:
                db.execute(
                    """UPDATE jobs SET notification_sent_at=?,
                    next_notification_attempt_at=NULL WHERE fingerprint=?""",
                    (_iso(now), fingerprint),
                )
            else:
                row = db.execute(
                    "SELECT notification_attempts FROM jobs WHERE fingerprint=?", (fingerprint,)
                ).fetchone()
                attempts = (row[0] if row else 0) + 1
                delay = min(3600, 30 * (2 ** min(attempts - 1, 7)))
                db.execute(
                    """UPDATE jobs SET notification_attempts=?, next_notification_attempt_at=?
                    WHERE fingerprint=?""",
                    (attempts, _iso(now + timedelta(seconds=delay)), fingerprint),
                )

    def record_scraper_attempt(
        self,
        company: str,
        *,
        succeeded: bool,
        job_count: int | None,
        error: str | None,
        attempted_at: datetime | None = None,
    ) -> None:
        now = attempted_at or datetime.now(UTC)
        with self.connect() as db:
            current = db.execute(
                "SELECT * FROM scraper_state WHERE company=?", (company,)
            ).fetchone()
            if succeeded:
                previous_normal = job_count
                if current and current["last_job_count"]:
                    previous_normal = current["last_job_count"]
                db.execute(
                    """INSERT INTO scraper_state(company,last_attempt_at,last_success_at,
                    consecutive_failures,last_job_count,previous_normal_job_count,last_error,
                    first_failure_at) VALUES(?,?,?,0,?,?,NULL,NULL)
                    ON CONFLICT(company) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                    last_success_at=excluded.last_success_at, consecutive_failures=0,
                    last_job_count=excluded.last_job_count,
                    previous_normal_job_count=excluded.previous_normal_job_count,
                    last_error=NULL, first_failure_at=NULL, operational_alert_sent_at=NULL""",
                    (company, _iso(now), _iso(now), job_count, previous_normal),
                )
            else:
                failures = (current["consecutive_failures"] if current else 0) + 1
                first_failure = (
                    current["first_failure_at"]
                    if current and current["first_failure_at"]
                    else _iso(now)
                )
                db.execute(
                    """INSERT INTO scraper_state(company,last_attempt_at,first_failure_at,
                    consecutive_failures,last_error) VALUES(?,?,?,?,?)
                    ON CONFLICT(company) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                    first_failure_at=excluded.first_failure_at,
                    consecutive_failures=excluded.consecutive_failures,last_error=excluded.last_error""",
                    (
                        company,
                        _iso(now),
                        first_failure,
                        failures,
                        (error or "unknown error")[:2000],
                    ),
                )

    def scraper_status(self) -> list[dict[str, object]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM scraper_state ORDER BY company").fetchall()
            return [{key: row[key] for key in row.keys()} for row in rows]

    def get_scraper_state(self, company: str) -> dict[str, object] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM scraper_state WHERE company=?", (company,)).fetchone()
            return {key: row[key] for key in row.keys()} if row else None

    def mark_operational_alert_sent(self, company: str, *, sent_at: datetime | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE scraper_state SET operational_alert_sent_at=? WHERE company=?",
                (_iso(sent_at or datetime.now(UTC)), company),
            )

    def export_debug(self) -> str:
        return json.dumps(self.scraper_status(), indent=2, default=str)
