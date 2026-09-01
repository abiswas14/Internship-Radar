from __future__ import annotations

import json
from datetime import UTC, datetime

from swe_job_radar.models import Job
from swe_job_radar.scrapers.base import CompanyScraper
from swe_job_radar.scrapers.shared.parsing import ScriptCaptureParser


class StripeScraper(CompanyScraper):
    company_name = "Stripe"
    careers_url = "https://stripe.com/careers/search"

    async def fetch_jobs(self) -> list[Job]:
        response = await self.http.get(self.careers_url)
        parser = ScriptCaptureParser(script_id="__NEXT_DATA__")
        parser.feed(response.text)
        if not parser.values:
            raise ValueError("Stripe official page no longer contains __NEXT_DATA__")
        payload = json.loads("".join(parser.values))
        index = payload["props"]["pageProps"]["jobIndexData"]
        listings = index["listings"]
        locations = index["filters"]["locations"]
        now = datetime.now(UTC)
        jobs: list[Job] = []
        for raw in listings:
            job_locations = [locations[i]["name"] for i in raw.get("locationIndices", [])]
            identifier = str(raw["greenhouseId"])
            slug = raw["slug"]
            jobs.append(
                Job(
                    company=self.company_name,
                    external_id=identifier,
                    title=raw["title"].strip(),
                    location="; ".join(job_locations) or None,
                    description=None,
                    job_url=f"https://stripe.com/careers/listing/{slug}/{identifier}",
                    apply_url=f"https://stripe.com/careers/apply/{slug}/{identifier}",
                    employment_type=raw.get("employmentType"),
                    date_posted=None,
                    first_seen_at=now,
                    source_url=self.careers_url,
                )
            )
        return jobs
