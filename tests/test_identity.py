from datetime import UTC, datetime

import pytest

from swe_job_radar.identity import canonicalize_url, job_fingerprint, normalize_text
from swe_job_radar.models import Job


def make_job(**overrides: object) -> Job:
    values = {
        "company": "Stripe",
        "external_id": "123",
        "title": "Software Engineer Intern",
        "location": "San Francisco, CA",
        "description": None,
        "job_url": "https://stripe.com/jobs/123?utm_source=x",
        "apply_url": None,
        "employment_type": "Intern",
        "date_posted": None,
        "first_seen_at": datetime.now(UTC),
        "source_url": "https://stripe.com/careers",
    }
    values.update(overrides)
    return Job(**values)


def test_normalization_and_canonicalization() -> None:
    assert normalize_text("  Software  ENGINEER ") == "software engineer"
    assert canonicalize_url("HTTPS://Example.COM/jobs//1/?utm_source=x&b=2&a=1#top") == (
        "https://example.com/jobs/1?a=1&b=2"
    )


def test_fingerprint_prefers_external_id() -> None:
    first = make_job(title="Old title", job_url="https://stripe.com/a")
    edited = make_job(title="New title", job_url="https://stripe.com/b?utm_campaign=x")
    assert job_fingerprint(first) == job_fingerprint(edited)


def test_fingerprint_without_id_ignores_tracking() -> None:
    first = make_job(external_id=None, job_url="https://stripe.com/jobs/1?utm_source=x")
    second = make_job(external_id=None, job_url="https://stripe.com/jobs/1?gclid=y")
    assert job_fingerprint(first) == job_fingerprint(second)


def test_job_rejects_malformed_urls() -> None:
    with pytest.raises(ValueError):
        make_job(job_url="/relative")
