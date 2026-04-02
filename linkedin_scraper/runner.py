from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from selenium import webdriver

from .browser import close_driver, setup_driver
from .config import ScraperConfig
from .exporters import export_links
from .google_search import search_google_for_linkedin_profile_links


@dataclass(frozen=True)
class ScrapeJobResult:
    total_links: int
    paths: dict[str, Path]


def run_scrape_job(config: ScraperConfig) -> ScrapeJobResult:
    driver: Optional[webdriver.Chrome] = None
    try:
        driver = setup_driver(headless=config.headless)
        driver, linkedin_links = search_google_for_linkedin_profile_links(
            driver,
            config.query,
            config.max_profiles,
            config.headless,
            config.challenge_timeout,
        )

        if not linkedin_links:
            raise RuntimeError("No LinkedIn links were found. Try a different query.")

        exported_paths = export_links(linkedin_links, config.query, config.output_base)
        return ScrapeJobResult(total_links=len(linkedin_links), paths=exported_paths)
    finally:
        close_driver(driver)
