from __future__ import annotations

from importlib import import_module

from swe_job_radar.http import HttpClient
from swe_job_radar.models import CompanyConfig
from swe_job_radar.scrapers.base import CompanyScraper


def create_scraper(config: CompanyConfig, http: HttpClient) -> CompanyScraper:
    if not config.scraper:
        raise ValueError(f"{config.slug} has no supported scraper")
    module_name, class_name = config.scraper.rsplit(":", 1)
    module = import_module(module_name)
    scraper_class = getattr(module, class_name)
    scraper = scraper_class(http)
    if not isinstance(scraper, CompanyScraper):
        raise TypeError(f"{config.scraper} does not implement CompanyScraper")
    return scraper
