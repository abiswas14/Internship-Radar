from swe_job_radar.scrapers.shared.ashby import AshbyBackedScraper


class OpenAIScraper(AshbyBackedScraper):
    company_name = "OpenAI"
    careers_url = "https://openai.com/careers/search/"
    ashby_board = "openai"
