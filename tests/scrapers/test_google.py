from conftest import load_fixture

from swe_job_radar.scrapers.google import GoogleScraper


def test_google_embedded_structured_data_fixture() -> None:
    jobs = GoogleScraper.parse_html(load_fixture("google.html"))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "81260991748154054"
    assert job.title == "Software Engineering Intern, BS, Summer 2027"
    assert job.location == "Mountain View, CA, USA"
    assert "graduating in May 2028" in (job.description or "")
    assert job.job_url.startswith(GoogleScraper.careers_url)
