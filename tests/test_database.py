from datetime import UTC, datetime, timedelta

from swe_job_radar.database import Database
from swe_job_radar.models import Classification, ClassificationResult, Job


def job(identifier: str, title: str = "Software Engineer Intern 2027") -> Job:
    return Job(
        company="Example",
        external_id=identifier,
        title=title,
        location="New York, NY",
        description="Summer 2027 internship",
        job_url=f"https://example.com/jobs/{identifier}",
        apply_url=None,
        employment_type="Intern",
        date_posted=None,
        first_seen_at=datetime.now(UTC),
        source_url="https://example.com/careers",
    )


def test_first_run_is_automatic_baseline_and_deduplicates(tmp_path) -> None:
    db = Database(tmp_path / "radar.db")
    first = db.observe_jobs("Example", [job("1")])
    assert first.baseline_created is True
    assert first.new_jobs == []
    second = db.observe_jobs("Example", [job("1")])
    assert second.baseline_created is False
    assert second.new_jobs == []
    third = db.observe_jobs("Example", [job("1"), job("2")])
    assert [value.external_id for value in third.new_jobs] == ["2"]


def test_short_reappearance_does_not_alert_but_repost_does(tmp_path) -> None:
    db = Database(tmp_path / "radar.db")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    db.observe_jobs("Example", [job("1")], observed_at=start)
    db.observe_jobs("Example", [], observed_at=start + timedelta(days=1))
    short = db.observe_jobs("Example", [job("1")], observed_at=start + timedelta(days=2))
    assert short.new_jobs == []
    db.observe_jobs("Example", [], observed_at=start + timedelta(days=3))
    repost = db.observe_jobs(
        "Example", [job("1")], observed_at=start + timedelta(days=34), repost_after_days=30
    )
    assert [value.external_id for value in repost.new_jobs] == ["1"]


def test_notification_success_is_idempotent(tmp_path) -> None:
    db = Database(tmp_path / "radar.db")
    db.observe_jobs("Example", [job("baseline")])
    new_job = job("new")
    db.observe_jobs("Example", [job("baseline"), new_job])
    result = ClassificationResult(Classification.INTERN_2027, "eligible", 0.99)
    db.set_classification(new_job, result)
    pending = db.pending_notifications()
    assert len(pending) == 1
    db.record_notification(pending[0]["fingerprint"], "stable-key", succeeded=True)
    assert db.pending_notifications() == []
    db.record_notification(pending[0]["fingerprint"], "stable-key", succeeded=True)
    with db.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM notification_attempts").fetchone()[0]
    assert count == 1


def test_failed_notification_remains_pending_after_backoff(tmp_path) -> None:
    db = Database(tmp_path / "radar.db")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    db.observe_jobs("Example", [job("baseline")], observed_at=start)
    new_job = job("new")
    db.observe_jobs("Example", [job("baseline"), new_job], observed_at=start)
    db.set_classification(
        new_job, ClassificationResult(Classification.INTERN_2027, "eligible", 0.99)
    )
    row = db.pending_notifications(now=start)[0]
    db.record_notification(
        row["fingerprint"], "stable-key", succeeded=False, error="SMTP down", attempted_at=start
    )
    assert db.pending_notifications(now=start + timedelta(seconds=10)) == []
    assert len(db.pending_notifications(now=start + timedelta(seconds=31))) == 1
