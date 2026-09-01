import asyncio

from conftest import FakeHttp, load_fixture

from swe_job_radar.scrapers.github import GitHubScraper


def test_github_jibe_fixture() -> None:
    scraper = GitHubScraper(FakeHttp({GitHubScraper.feed_url: load_fixture("github.json")}))
    jobs = asyncio.run(scraper.fetch_jobs())
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "5741"
    assert job.location == "United States"
    assert job.description == "Early career candidates with 0-1 years of experience."
    assert job.job_url.endswith("/5741?lang=en-us")
