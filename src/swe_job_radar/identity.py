from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from swe_job_radar.models import Job

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "gh_src",
    "ref",
    "referrer",
    "source",
    "src",
}


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        query.append((key, value))
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    host = (parts.hostname or "").casefold()
    port = parts.port
    netloc = host if not port or (parts.scheme == "https" and port == 443) else f"{host}:{port}"
    return urlunsplit((parts.scheme.casefold(), netloc, path, urlencode(sorted(query)), ""))


def job_fingerprint(job: Job) -> str:
    if job.external_id:
        stable = f"{normalize_text(job.company)}\0id\0{normalize_text(job.external_id)}"
    else:
        stable = "\0".join(
            (
                normalize_text(job.company),
                normalize_text(job.title),
                normalize_text(job.location),
                canonicalize_url(job.job_url),
            )
        )
    return hashlib.sha256(stable.encode()).hexdigest()
