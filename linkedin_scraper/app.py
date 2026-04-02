from .config import parse_config
from .runner import run_scrape_job


def run() -> None:
    config = parse_config()
    try:
        print("\n" + "=" * 70)
        print("STEP 1: COLLECTING LINKEDIN PROFILE LINKS")
        print("=" * 70)
        result = run_scrape_job(config)

        print("\n" + "=" * 70)
        print("EXPORT COMPLETE")
        print("=" * 70)
        print(f"Total links exported: {result.total_links}")
        print(f"JSON: {result.paths['json']}")
        print(f"Excel: {result.paths['excel']}")
        print(f"PDF: {result.paths['pdf']}")

    except Exception as exc:
        print(f"Error in main execution: {exc}")
        raise
