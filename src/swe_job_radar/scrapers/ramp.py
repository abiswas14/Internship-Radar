from swe_job_radar.scrapers.shared.ashby import AshbyBackedScraper


class RampScraper(AshbyBackedScraper):
    company_name = "Ramp"
    careers_url = "https://ramp.com/careers"
    ashby_board = "ramp"
