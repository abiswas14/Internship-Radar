import asyncio
from datetime import UTC, datetime

import pytest

from swe_job_radar.classification.fallback import StructuredJsonLLMFallback
from swe_job_radar.models import Job


def job(title: str) -> Job:
    return Job(
        company="Example",
        external_id="1",
        title=title,
        location="New York, NY",
        description="",
        job_url="https://example.com/jobs/1",
        apply_url=None,
        employment_type=None,
        date_posted=None,
        first_seen_at=datetime.now(UTC),
        source_url="https://example.com/careers",
    )


def test_structured_json_fallback_validation() -> None:
    async def request(_: str) -> dict[str, object]:
        return {
            "classification": "NEW_GRAD_2027",
            "confidence": 0.91,
            "reason": "Requires zero prior professional experience.",
        }

    result = asyncio.run(StructuredJsonLLMFallback(request).classify(job("Software Engineer")))
    assert result is not None
    assert result.classification.value == "NEW_GRAD_2027"


def test_structured_json_fallback_rejects_bad_output() -> None:
    async def request(_: str) -> str:
        return '{"classification":"UNKNOWN"}'

    with pytest.raises(ValueError):
        asyncio.run(StructuredJsonLLMFallback(request).classify(job("Software Engineer")))
