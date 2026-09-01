from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from swe_job_radar.models import Job
from swe_job_radar.scrapers.base import CompanyScraper
from swe_job_radar.scrapers.shared.parsing import html_to_text, slugify


class GoogleScraper(CompanyScraper):
    """Parse Google's structured AF data embedded in its official result pages.

    Google has thousands of openings. Polling the most recent U.S. results for three
    broad technical terms catches new target roles without downloading hundreds of pages.
    """

    company_name = "Google"
    careers_url = "https://www.google.com/about/careers/applications/jobs/results/"
    search_terms = ("engineer", "developer", "intern")

    async def fetch_jobs(self) -> list[Job]:
        responses = await asyncio.gather(
            *(
                self.http.get(
                    self.careers_url,
                    params={
                        "q": term,
                        "location": "United States",
                        "sort_by": "date",
                        "page": 1,
                    },
                )
                for term in self.search_terms
            )
        )
        jobs: dict[str, Job] = {}
        for response in responses:
            for job in self.parse_html(response.text):
                jobs[job.external_id or job.job_url] = job
        if not jobs:
            raise ValueError("Google official pages yielded no structured jobs")
        return list(jobs.values())

    @classmethod
    def parse_html(cls, html: str) -> list[Job]:
        match = re.search(
            r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel: \{\}\}\);",
            html,
            flags=re.DOTALL,
        )
        if not match:
            raise ValueError("Google careers ds:1 structured data was not found")
        data = json.loads(match.group(1))
        raw_jobs = data[0]
        if not isinstance(raw_jobs, list):
            raise ValueError("Google careers ds:1 job list has changed")
        now = datetime.now(UTC)
        return [cls._normalize(item, now) for item in raw_jobs if cls._valid_item(item)]

    @staticmethod
    def _valid_item(item: Any) -> bool:
        return isinstance(item, list) and len(item) >= 19 and item[0] and item[1]

    @classmethod
    def _normalize(cls, raw: list[Any], now: datetime) -> Job:
        external_id = str(raw[0])
        title = str(raw[1]).strip()
        locations = []
        for location in raw[9] or []:
            if isinstance(location, list) and location:
                locations.append(str(location[0]))
        description_parts = []
        for index in (3, 4, 10, 18):
            value = raw[index] if index < len(raw) else None
            if isinstance(value, list) and len(value) > 1 and value[1]:
                description_parts.append(str(value[1]))
        timestamp = raw[12][0] if len(raw) > 12 and isinstance(raw[12], list) else None
        posted = datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else None
        slug = slugify(title)
        job_url = f"{cls.careers_url}{external_id}-{slug}/"
        apply_url = raw[2] if isinstance(raw[2], str) and raw[2].startswith("http") else None
        return Job(
            company=cls.company_name,
            external_id=external_id,
            title=title,
            location="; ".join(locations) or None,
            description=html_to_text("\n".join(description_parts)),
            job_url=job_url,
            apply_url=apply_url,
            employment_type=None,
            date_posted=posted,
            first_seen_at=now,
            source_url=cls.careers_url,
        )
