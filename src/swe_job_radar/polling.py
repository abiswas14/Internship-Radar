from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic

from swe_job_radar.classification import RuleBasedClassifier
from swe_job_radar.classification.fallback import AmbiguousClassificationFallback
from swe_job_radar.database import Database
from swe_job_radar.models import (
    Classification,
    ClassificationResult,
    CompanyConfig,
    Job,
)
from swe_job_radar.notifications.base import Notifier
from swe_job_radar.scrapers.base import CompanyScraper

logger = logging.getLogger(__name__)

HEALTH_ALERT_AFTER = {
    "critical": timedelta(hours=2),
    "high": timedelta(hours=6),
    "quant": timedelta(hours=12),
}


@dataclass(slots=True)
class PollTarget:
    config: CompanyConfig
    scraper: CompanyScraper


class Monitor:
    def __init__(
        self,
        *,
        targets: list[PollTarget],
        database: Database,
        classifier: RuleBasedClassifier,
        notifier: Notifier | None,
        concurrency: int = 8,
        repost_after_days: int = 30,
        ambiguous_fallback: AmbiguousClassificationFallback | None = None,
    ) -> None:
        self.targets = targets
        self.database = database
        self.classifier = classifier
        self.notifier = notifier
        self.semaphore = asyncio.Semaphore(concurrency)
        self.notification_lock = asyncio.Lock()
        self.repost_after_days = repost_after_days
        self.ambiguous_fallback = ambiguous_fallback
        self.config_by_company = {target.config.name: target.config for target in targets}

    async def poll_company(self, target: PollTarget, *, force_baseline: bool = False) -> bool:
        start = monotonic()
        now = datetime.now(UTC)
        async with self.semaphore:
            try:
                jobs = await target.scraper.fetch_jobs()
                if not jobs:
                    raise RuntimeError("suspicious zero-job response; active jobs were preserved")
                observation = self.database.observe_jobs(
                    target.config.name,
                    jobs,
                    observed_at=now,
                    force_baseline=force_baseline,
                    repost_after_days=self.repost_after_days,
                )
                relevant = 0
                for job in observation.new_jobs:
                    result = self.classifier.classify(job, target.config.priority)
                    if (
                        result.classification is Classification.RELEVANT_BUT_AMBIGUOUS
                        and self.ambiguous_fallback is not None
                    ):
                        fallback_result = await self.ambiguous_fallback.classify(job)
                        if fallback_result is not None:
                            result = fallback_result
                    self.database.set_classification(job, result)
                    if result.classification is not Classification.IRRELEVANT:
                        relevant += 1
                self.database.record_scraper_attempt(
                    target.config.name, succeeded=True, job_count=len(jobs), error=None
                )
                logger.info(
                    "poll_complete",
                    extra={
                        "company": target.config.name,
                        "priority": target.config.priority.value,
                        "scraper": type(target.scraper).__name__,
                        "duration_seconds": round(monotonic() - start, 3),
                        "jobs_returned": len(jobs),
                        "new_jobs": len(observation.new_jobs),
                        "relevant_jobs": relevant,
                        "baseline_created": observation.baseline_created,
                    },
                )
                return True
            except Exception as exc:
                self.database.record_scraper_attempt(
                    target.config.name,
                    succeeded=False,
                    job_count=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
                logger.exception(
                    "poll_failed",
                    extra={
                        "company": target.config.name,
                        "priority": target.config.priority.value,
                        "scraper": type(target.scraper).__name__,
                        "duration_seconds": round(monotonic() - start, 3),
                    },
                )
                await self._maybe_send_operational_alert(target)
                return False

    async def check_once(self, *, force_baseline: bool = False) -> bool:
        results = await asyncio.gather(
            *(self.poll_company(target, force_baseline=force_baseline) for target in self.targets)
        )
        if not force_baseline:
            await self.send_pending()
        return all(results)

    async def send_pending(self) -> int:
        # Independent company loops may finish together. Serialize the select/send/update
        # transaction in-process so they cannot race and email the same pending row twice.
        async with self.notification_lock:
            return await self._send_pending_locked()

    async def _send_pending_locked(self) -> int:
        if self.notifier is None:
            pending = len(self.database.pending_notifications())
            if pending:
                logger.warning("email_not_configured", extra={"pending_notifications": pending})
            return 0
        sent = 0
        for row in self.database.pending_notifications():
            job = self._job_from_row(row)
            config = self.config_by_company.get(job.company)
            if not config:
                continue
            result = ClassificationResult(
                Classification(row["classification"]),
                row["classification_reason"],
                float(row["classification_confidence"] or 0),
            )
            fingerprint = row["fingerprint"]
            idempotency_key = hashlib.sha256(
                f"{fingerprint}:{row['first_seen_at']}:{row['classification']}".encode()
            ).hexdigest()[:40]
            try:
                await self.notifier.send(
                    job, result, config.priority, idempotency_key=idempotency_key
                )
            except Exception as exc:
                self.database.record_notification(
                    fingerprint,
                    idempotency_key,
                    succeeded=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
                logger.exception("notification_failed", extra={"company": job.company})
            else:
                self.database.record_notification(fingerprint, idempotency_key, succeeded=True)
                sent += 1
                logger.info(
                    "notification_sent",
                    extra={"company": job.company, "fingerprint": fingerprint},
                )
        return sent

    async def run_forever(self) -> None:
        await asyncio.gather(*(self._company_loop(target) for target in self.targets))

    async def _company_loop(self, target: PollTarget) -> None:
        await asyncio.sleep(random.uniform(0, target.config.jitter_seconds))
        while True:
            await self.poll_company(target)
            await self.send_pending()
            delay = target.config.polling_interval_seconds + random.uniform(
                -target.config.jitter_seconds, target.config.jitter_seconds
            )
            await asyncio.sleep(max(60, delay))

    async def _maybe_send_operational_alert(self, target: PollTarget) -> None:
        if self.notifier is None:
            return
        state = self.database.get_scraper_state(target.config.name)
        if not state or state.get("operational_alert_sent_at"):
            return
        first_failure_value = state.get("first_failure_at")
        if not isinstance(first_failure_value, str):
            return
        first_failure = datetime.fromisoformat(first_failure_value)
        threshold = HEALTH_ALERT_AFTER[target.config.priority.value]
        if datetime.now(UTC) - first_failure < threshold:
            return
        key = hashlib.sha256(
            f"health:{target.config.name}:{first_failure_value}".encode()
        ).hexdigest()[:40]
        try:
            await self.notifier.send_operational(
                f"{target.config.name} scraper unavailable",
                "\n".join(
                    (
                        "SWE Job Radar scraper health alert",
                        "",
                        f"Company: {target.config.name}",
                        f"Priority: {target.config.priority.value.upper()}",
                        f"Continuous failure since: {first_failure_value}",
                        f"Consecutive failures: {state.get('consecutive_failures')}",
                        f"Most recent error: {state.get('last_error')}",
                        "",
                        "Other companies continue to be monitored.",
                    )
                ),
                idempotency_key=key,
            )
        except Exception:
            logger.exception(
                "operational_notification_failed",
                extra={"company": target.config.name},
            )
        else:
            self.database.mark_operational_alert_sent(target.config.name)

    @staticmethod
    def _job_from_row(row: object) -> Job:
        return Job(
            company=row["company"],
            external_id=row["external_id"],
            title=row["title"],
            location=row["location"],
            description=row["description"],
            job_url=row["job_url"],
            apply_url=row["apply_url"],
            employment_type=row["employment_type"],
            date_posted=datetime.fromisoformat(row["date_posted"]) if row["date_posted"] else None,
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            source_url=row["source_url"],
        )
