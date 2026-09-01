import asyncio
from datetime import UTC, datetime

from swe_job_radar.classification import RuleBasedClassifier
from swe_job_radar.database import Database
from swe_job_radar.models import CompanyConfig, Job, Priority
from swe_job_radar.polling import Monitor, PollTarget
from swe_job_radar.scrapers.base import CompanyScraper


def one_job() -> Job:
    return Job(
        company="Example",
        external_id="1",
        title="Software Engineer Intern 2027",
        location="New York, NY",
        description="Summer 2027",
        job_url="https://example.com/jobs/1",
        apply_url=None,
        employment_type="Intern",
        date_posted=None,
        first_seen_at=datetime.now(UTC),
        source_url="https://example.com/careers",
    )


class SequenceScraper(CompanyScraper):
    company_name = "Example"
    careers_url = "https://example.com/careers"

    def __init__(self, values: list[list[Job]]) -> None:
        self.values = values

    async def fetch_jobs(self) -> list[Job]:
        return self.values.pop(0)


def test_zero_result_is_failure_and_does_not_deactivate_jobs(tmp_path) -> None:
    db = Database(tmp_path / "radar.db")
    config = CompanyConfig(
        slug="example",
        name="Example",
        enabled=True,
        priority=Priority.CRITICAL,
        careers_url="https://example.com/careers",
        source_mechanism="fixture",
        polling_interval_seconds=120,
        scraper="test:SequenceScraper",
        status="supported",
    )
    scraper = SequenceScraper([[one_job()], []])
    monitor = Monitor(
        targets=[PollTarget(config, scraper)],
        database=db,
        classifier=RuleBasedClassifier(),
        notifier=None,
    )
    asyncio.run(monitor.poll_company(monitor.targets[0]))
    asyncio.run(monitor.poll_company(monitor.targets[0]))
    with db.connect() as connection:
        active = connection.execute("SELECT active FROM jobs").fetchone()[0]
        failures = connection.execute(
            "SELECT consecutive_failures FROM scraper_state WHERE company='Example'"
        ).fetchone()[0]
    assert active == 1
    assert failures == 1
