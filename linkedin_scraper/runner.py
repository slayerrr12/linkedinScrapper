from dataclasses import dataclass
from pathlib import Path
from .config import ScraperConfig
from .exporters import export_links
from .search_api import search_linkedin_profile_links


@dataclass(frozen=True)
class ScrapeJobResult:
    total_links: int
    paths: dict[str, Path]


def run_scrape_job(config: ScraperConfig) -> ScrapeJobResult:
    linkedin_links = search_linkedin_profile_links(config)
    if not linkedin_links:
        raise RuntimeError("No LinkedIn links were found. Try a different query.")

    exported_paths = export_links(linkedin_links, config.query, config.output_base)
    return ScrapeJobResult(total_links=len(linkedin_links), paths=exported_paths)
