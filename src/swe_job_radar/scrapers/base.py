from __future__ import annotations

from abc import ABC, abstractmethod

from swe_job_radar.http import HttpClient
from swe_job_radar.models import Job


class CompanyScraper(ABC):
    company_name: str
    careers_url: str

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    @abstractmethod
    async def fetch_jobs(self) -> list[Job]:
        """Fetch and normalize every job visible through this source."""
