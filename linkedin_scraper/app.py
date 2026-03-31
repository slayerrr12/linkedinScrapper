from typing import Optional

from selenium import webdriver

from .browser import close_driver, setup_driver
from .config import parse_config
from .exporters import export_links
from .google_search import search_google_for_linkedin_profile_links


def run() -> None:
    config = parse_config()

    driver: Optional[webdriver.Chrome] = None
    try:
        driver = setup_driver(headless=config.headless)

        print("\n" + "=" * 70)
        print("STEP 1: COLLECTING LINKEDIN PROFILE LINKS")
        print("=" * 70)
        driver, linkedin_links = search_google_for_linkedin_profile_links(
            driver,
            config.query,
            config.max_profiles,
            config.headless,
            config.challenge_timeout,
        )

        if not linkedin_links:
            print("No LinkedIn links were found. Try a different query.")
            return

        exported_paths = export_links(linkedin_links, config.query, config.output_base)

        print("\n" + "=" * 70)
        print("EXPORT COMPLETE")
        print("=" * 70)
        print(f"Total links exported: {len(linkedin_links)}")
        print(f"JSON: {exported_paths['json']}")
        print(f"Excel: {exported_paths['excel']}")
        print(f"PDF: {exported_paths['pdf']}")

    except Exception as exc:
        print(f"Error in main execution: {exc}")
        raise
    finally:
        close_driver(driver)
        print("\nBrowser closed")
