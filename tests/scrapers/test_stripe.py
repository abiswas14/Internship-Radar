import asyncio

from conftest import FakeHttp, load_fixture

from swe_job_radar.scrapers.stripe import StripeScraper


def test_stripe_next_data_fixture() -> None:
    scraper = StripeScraper(FakeHttp({StripeScraper.careers_url: load_fixture("stripe.html")}))
    jobs = asyncio.run(scraper.fetch_jobs())
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "8130805"
    assert job.location == "San Francisco, CA"
    assert job.job_url.endswith("/software-engineer-intern-summer-or-winter/8130805")
    assert job.apply_url and "/careers/apply/" in job.apply_url
