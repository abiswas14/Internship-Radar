from __future__ import annotations

from datetime import UTC, datetime

from swe_job_radar.models import Job
from swe_job_radar.scrapers.base import CompanyScraper
from swe_job_radar.scrapers.shared.parsing import html_to_text


class JaneStreetScraper(CompanyScraper):
    company_name = "Jane Street"
    careers_url = "https://www.janestreet.com/join-jane-street/open-roles/"
    feed_url = "https://www.janestreet.com/jobs/main.json"

    async def fetch_jobs(self) -> list[Job]:
        response = await self.http.get(self.feed_url)
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Jane Street official feed is not an array")
        now = datetime.now(UTC)
        return [
            Job(
                company=self.company_name,
                external_id=str(raw["id"]),
                title=raw["position"].strip(),
                location=raw.get("city"),
                description=html_to_text(raw.get("overview")),
                job_url=f"https://www.janestreet.com/join-jane-street/position/{raw['id']}/",
                apply_url=f"https://www.janestreet.com/join-jane-street/position/{raw['id']}/",
                employment_type=raw.get("availability"),
                date_posted=None,
                first_seen_at=now,
                source_url=self.careers_url,
            )
            for raw in payload
        ]
