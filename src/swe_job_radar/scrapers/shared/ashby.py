from __future__ import annotations

from datetime import UTC, datetime

from swe_job_radar.models import Job
from swe_job_radar.scrapers.base import CompanyScraper
from swe_job_radar.scrapers.shared.parsing import parse_datetime


class AshbyBackedScraper(CompanyScraper):
    ashby_board: str

    @property
    def feed_url(self) -> str:
        return f"https://api.ashbyhq.com/posting-api/job-board/{self.ashby_board}"

    async def fetch_jobs(self) -> list[Job]:
        response = await self.http.get(self.feed_url, params={"includeCompensation": "false"})
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError(f"{self.company_name}: Ashby response missing jobs array")
        now = datetime.now(UTC)
        jobs: list[Job] = []
        for raw in payload["jobs"]:
            if not raw.get("isListed", True):
                continue
            locations = [raw.get("location")]
            locations.extend(item.get("location") for item in raw.get("secondaryLocations", []))
            location = "; ".join(dict.fromkeys(item for item in locations if item)) or None
            jobs.append(
                Job(
                    company=self.company_name,
                    external_id=str(raw["id"]),
                    title=str(raw["title"]).strip(),
                    location=location,
                    description=raw.get("descriptionPlain"),
                    job_url=raw["jobUrl"],
                    apply_url=raw.get("applyUrl"),
                    employment_type=raw.get("employmentType"),
                    date_posted=parse_datetime(raw.get("publishedAt")),
                    first_seen_at=now,
                    source_url=self.careers_url,
                )
            )
        return jobs
