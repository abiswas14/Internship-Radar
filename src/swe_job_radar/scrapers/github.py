from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime

from swe_job_radar.models import Job
from swe_job_radar.scrapers.base import CompanyScraper
from swe_job_radar.scrapers.shared.parsing import html_to_text, parse_datetime


class GitHubScraper(CompanyScraper):
    company_name = "GitHub"
    careers_url = "https://www.github.careers/careers-home/jobs"
    feed_url = "https://www.github.careers/api/jobs"

    async def fetch_jobs(self) -> list[Job]:
        # Jibe currently rejects limits above 100 with HTTP 422.
        response = await self.http.get(self.feed_url, params={"page": 1, "limit": 100})
        payload = response.json()
        raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(raw_jobs, list):
            raise ValueError("GitHub official Jibe response missing jobs array")
        total = int(payload.get("totalCount", len(raw_jobs)))
        page_count = math.ceil(total / 100)
        if page_count > 1:
            responses = await asyncio.gather(
                *(
                    self.http.get(self.feed_url, params={"page": page, "limit": 100})
                    for page in range(2, page_count + 1)
                )
            )
            for page_response in responses:
                page_payload = page_response.json()
                page_jobs = page_payload.get("jobs") if isinstance(page_payload, dict) else None
                if not isinstance(page_jobs, list):
                    raise ValueError("GitHub official Jibe pagination schema changed")
                raw_jobs.extend(page_jobs)
        now = datetime.now(UTC)
        jobs: list[Job] = []
        for item in raw_jobs:
            raw = item.get("data", item)
            slug = str(raw["slug"])
            jobs.append(
                Job(
                    company=self.company_name,
                    external_id=str(raw.get("req_id") or slug),
                    title=raw["title"].strip(),
                    location=raw.get("full_location") or raw.get("location_name"),
                    description=html_to_text(raw.get("description")),
                    job_url=f"https://www.github.careers/careers-home/jobs/{slug}?lang=en-us",
                    apply_url=raw.get("apply_url"),
                    employment_type=raw.get("employment_type"),
                    date_posted=parse_datetime(raw.get("posted_date")),
                    first_seen_at=now,
                    source_url=self.careers_url,
                )
            )
        return jobs
