from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from swe_job_radar.models import CompanyConfig, Priority

DEFAULT_USER_AGENT = "SWEJobRadar/0.1 (official public careers monitor)"


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    concurrency: int = 8
    per_domain_concurrency: int = 2
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    repost_after_days: int = 30
    user_agent: str = DEFAULT_USER_AGENT


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_companies(path: Path = Path("config/companies.yaml")) -> dict[str, CompanyConfig]:
    raw = _read_yaml(path).get("companies", {})
    companies: dict[str, CompanyConfig] = {}
    for slug, value in raw.items():
        companies[slug] = CompanyConfig(
            slug=slug,
            name=value["name"],
            enabled=bool(value.get("enabled", False)),
            priority=Priority(value["priority"]),
            careers_url=value.get("careers_url"),
            source_mechanism=value.get("source_mechanism", "unverified"),
            polling_interval_seconds=int(value.get("polling_interval_seconds", 180)),
            scraper=value.get("scraper"),
            status=value.get("status", "unsupported"),
            notes=value.get("notes", ""),
            jitter_seconds=int(value.get("jitter_seconds", 20)),
        )
    return companies


def load_settings(path: Path = Path("config/settings.yaml")) -> Settings:
    raw = _read_yaml(path)
    database_path = Path(
        os.getenv("DATABASE_PATH", raw.get("database_path", "data/swe-job-radar.db"))
    )
    return Settings(
        database_path=database_path,
        concurrency=int(raw.get("concurrency", 8)),
        per_domain_concurrency=int(raw.get("per_domain_concurrency", 2)),
        request_timeout_seconds=float(raw.get("request_timeout_seconds", 30)),
        max_retries=int(raw.get("max_retries", 3)),
        repost_after_days=int(raw.get("repost_after_days", 30)),
        user_agent=raw.get("user_agent", DEFAULT_USER_AGENT),
    )
