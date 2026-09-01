import asyncio

from conftest import FakeHttp, load_fixture

from swe_job_radar.scrapers.openai import OpenAIScraper
from swe_job_radar.scrapers.ramp import RampScraper


def test_openai_and_ramp_company_modules_use_shared_verified_schema() -> None:
    fixture = load_fixture("ashby.json")
    for scraper_class in (OpenAIScraper, RampScraper):
        scraper = scraper_class(FakeHttp({scraper_class(FakeHttp({})).feed_url: fixture}))
        jobs = asyncio.run(scraper.fetch_jobs())
        assert len(jobs) == 1
        assert jobs[0].external_id == "job-123"
        assert jobs[0].title == "Software Engineer Intern, Summer 2027"
        assert jobs[0].location == "San Francisco, CA; New York, NY"
        assert jobs[0].company == scraper.company_name
