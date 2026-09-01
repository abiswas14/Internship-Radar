from __future__ import annotations

from abc import ABC, abstractmethod

from swe_job_radar.models import ClassificationResult, Job, Priority


class Notifier(ABC):
    @abstractmethod
    async def send(
        self,
        job: Job,
        result: ClassificationResult,
        priority: Priority,
        *,
        idempotency_key: str,
    ) -> None:
        """Send exactly one actionable notification or raise."""

    @abstractmethod
    async def send_operational(self, subject: str, body: str, *, idempotency_key: str) -> None:
        """Send a clearly distinguished service-health notification or raise."""
