from datetime import UTC, datetime

from swe_job_radar.models import Classification, ClassificationResult, Job, Priority
from swe_job_radar.notifications.email import format_body, format_subject


def test_email_formatting_is_actionable() -> None:
    job = Job(
        company="Stripe",
        external_id="1",
        title="Software Engineer",
        location="San Francisco, CA",
        description=None,
        job_url="https://stripe.com/careers/listing/software-engineer/1",
        apply_url="https://stripe.com/careers/apply/software-engineer/1",
        employment_type="Full time",
        date_posted=None,
        first_seen_at=datetime(2026, 9, 3, 18, 3, 17, tzinfo=UTC),
        source_url="https://stripe.com/careers/search",
    )
    result = ClassificationResult(Classification.NEW_GRAD_2027, "0-1 years", 0.91)
    assert format_subject(job, result, Priority.CRITICAL) == (
        "🚨 [NEW GRAD 2027] Stripe — Software Engineer"
    )
    body = format_body(job, result, Priority.CRITICAL)
    assert body.index("APPLY:") < body.index("Company:")
    assert "2026-09-03 14:03:17 EDT" in body
    assert job.apply_url in body
    assert job.job_url in body


def test_ambiguous_and_quant_subjects() -> None:
    base = Job(
        company="Jane Street",
        external_id="1",
        title="Software Engineer",
        location="NYC",
        description=None,
        job_url="https://www.janestreet.com/join-jane-street/position/1/",
        apply_url=None,
        employment_type=None,
        date_posted=None,
        first_seen_at=datetime.now(UTC),
        source_url="https://www.janestreet.com/join-jane-street/open-roles/",
    )
    new_grad = ClassificationResult(Classification.NEW_GRAD_2027, "new grad", 0.9)
    ambiguous = ClassificationResult(Classification.RELEVANT_BUT_AMBIGUOUS, "review", 0.7)
    assert format_subject(base, new_grad, Priority.QUANT).startswith("📈 [NEW GRAD 2027 SWE]")
    assert format_subject(base, ambiguous, Priority.QUANT).startswith("⚠️ [REVIEW]")
