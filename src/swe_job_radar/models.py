from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlparse


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    QUANT = "quant"


class Classification(StrEnum):
    INTERN_2027 = "INTERN_2027"
    NEW_GRAD_2027 = "NEW_GRAD_2027"
    RELEVANT_BUT_AMBIGUOUS = "RELEVANT_BUT_AMBIGUOUS"
    IRRELEVANT = "IRRELEVANT"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Job:
    company: str
    external_id: str | None
    title: str
    location: str | None
    description: str | None
    job_url: str
    apply_url: str | None
    employment_type: str | None
    date_posted: datetime | None
    first_seen_at: datetime = field(default_factory=utc_now)
    source_url: str = ""

    def __post_init__(self) -> None:
        if not self.company.strip():
            raise ValueError("company is required")
        if not self.title.strip():
            raise ValueError("title is required")
        for name in ("job_url", "source_url"):
            value = getattr(self, name)
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{name} must be an absolute HTTP(S) URL")
        if self.apply_url:
            parsed = urlparse(self.apply_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("apply_url must be an absolute HTTP(S) URL")
        for name in ("date_posted", "first_seen_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: Classification
    reason: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CompanyConfig:
    slug: str
    name: str
    enabled: bool
    priority: Priority
    careers_url: str | None
    source_mechanism: str
    polling_interval_seconds: int
    scraper: str | None
    status: str
    notes: str = ""
    jitter_seconds: int = 20

    def __post_init__(self) -> None:
        if self.polling_interval_seconds < 60:
            raise ValueError(f"{self.slug}: polling interval may not be under 60 seconds")
        if self.enabled and (not self.careers_url or not self.scraper):
            raise ValueError(f"{self.slug}: enabled companies require a URL and scraper")
