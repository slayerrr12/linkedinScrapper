import argparse
import tkinter as tk
from dataclasses import dataclass
from tkinter import simpledialog


DEFAULT_SEARCH_QUERY = "Mtech cse 27 iit Guwahati"
DEFAULT_MAX_PROFILES = 25
DEFAULT_OUTPUT_BASE = "results"
DEFAULT_HEADLESS = False
DEFAULT_CHALLENGE_TIMEOUT = 600


@dataclass(frozen=True)
class ScraperConfig:
    query: str
    max_profiles: int
    output_base: str
    headless: bool
    challenge_timeout: int


def prompt_runtime_settings(default_query: str, default_max_profiles: int) -> tuple[str, int]:
    try:
        root = tk.Tk()
    except tk.TclError:
        print("GUI prompt could not be opened. Falling back to the built-in query and max profile defaults.")
        return default_query, default_max_profiles

    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    try:
        query = simpledialog.askstring(
            "LinkedIn Link Scraper",
            "Enter the Google search query for LinkedIn profiles:",
            initialvalue=default_query,
            parent=root,
        )
        if query is None:
            query = default_query
        query = query.strip() or default_query

        max_profiles = simpledialog.askinteger(
            "LinkedIn Link Scraper",
            "Enter the maximum number of links to collect:",
            initialvalue=default_max_profiles,
            minvalue=1,
            parent=root,
        )
        if max_profiles is None:
            max_profiles = default_max_profiles

        return query, max_profiles
    finally:
        root.destroy()


def validate_config(config: ScraperConfig) -> None:
    if not config.query:
        raise ValueError("The search query cannot be empty.")
    if config.max_profiles <= 0:
        raise ValueError("--max-profiles must be greater than 0.")
    if config.challenge_timeout <= 0:
        raise ValueError("--challenge-timeout must be greater than 0.")


def parse_config() -> ScraperConfig:
    parser = argparse.ArgumentParser(
        description="Search Google for LinkedIn profile links and export them to PDF, JSON, and Excel."
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_SEARCH_QUERY,
        help="Google query used with site:linkedin.com/in.",
    )
    parser.add_argument(
        "--max-profiles",
        type=int,
        default=DEFAULT_MAX_PROFILES,
        help="Maximum number of LinkedIn profile links to collect.",
    )
    parser.add_argument(
        "--output-base",
        default=DEFAULT_OUTPUT_BASE,
        help="Base output path without extension. Example: results/output_links",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_HEADLESS,
        help="Run Chrome in headless mode.",
    )
    parser.add_argument(
        "--challenge-timeout",
        type=int,
        default=DEFAULT_CHALLENGE_TIMEOUT,
        help="Seconds to wait for you to manually solve a CAPTCHA or checkpoint in the browser.",
    )

    args = parser.parse_args()
    query, max_profiles = prompt_runtime_settings(args.query, args.max_profiles)
    config = ScraperConfig(
        query=query,
        max_profiles=max_profiles,
        output_base=args.output_base,
        headless=args.headless,
        challenge_timeout=args.challenge_timeout,
    )
    validate_config(config)
    return config
