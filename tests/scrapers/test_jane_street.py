import asyncio

from conftest import FakeHttp, load_fixture

from swe_job_radar.scrapers.jane_street import JaneStreetScraper


def test_jane_street_official_json_fixture() -> None:
    scraper = JaneStreetScraper(
        FakeHttp({JaneStreetScraper.feed_url: load_fixture("jane_street.json")})
    )
    jobs = asyncio.run(scraper.fetch_jobs())
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "12345"
    assert job.employment_type == "Full-Time: New Grad"
    assert job.location == "NYC"
    assert "reliable trading systems" in (job.description or "")
