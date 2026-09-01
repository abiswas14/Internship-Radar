from swe_job_radar.config import load_companies


def test_allowlist_and_enabled_sources() -> None:
    companies = load_companies()
    # The brief numbers 100 entries, but item 90 is prose rather than a company.
    assert len(companies) == 99
    assert {slug for slug, value in companies.items() if value.enabled} == {
        "openai",
        "google",
        "stripe",
        "ramp",
        "github",
        "jane_street",
    }
    assert all(value.careers_url is None for value in companies.values() if not value.enabled)
