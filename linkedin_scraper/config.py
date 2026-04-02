import argparse
import os
from dataclasses import dataclass


DEFAULT_SEARCH_QUERY = "Mtech cse 27 iit Guwahati"
DEFAULT_MAX_PROFILES = 25
DEFAULT_OUTPUT_BASE = "results"
DEFAULT_SERPAPI_GOOGLE_DOMAIN = "google.com"
DEFAULT_SERPAPI_LANGUAGE = "en"
DEFAULT_SERPAPI_COUNTRY = ""


@dataclass(frozen=True)
class ScraperConfig:
    query: str
    max_profiles: int
    output_base: str
    serpapi_api_key: str
    google_domain: str
    language: str
    country: str


def prompt_runtime_settings(default_query: str, default_max_profiles: int) -> tuple[str, int]:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError:
        print("Tkinter is not available in this environment. Falling back to the built-in query and max profile defaults.")
        return default_query, default_max_profiles

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
            "Enter the search query for LinkedIn profiles:",
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
    if not config.serpapi_api_key:
        raise ValueError("A SerpApi API key is required. Use --api-key or set SERPAPI_API_KEY.")


def parse_config() -> ScraperConfig:
    parser = argparse.ArgumentParser(
        description="Search for LinkedIn profile links through SerpApi and export them to PDF, JSON, and Excel."
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_SEARCH_QUERY,
        help="Search query used with site:linkedin.com/in.",
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
        "--api-key",
        default=os.getenv("SERPAPI_API_KEY", ""),
        help="SerpApi API key. Can also be provided via SERPAPI_API_KEY.",
    )
    parser.add_argument(
        "--google-domain",
        default=os.getenv("SERPAPI_GOOGLE_DOMAIN", DEFAULT_SERPAPI_GOOGLE_DOMAIN),
        help="Google domain used by SerpApi, for example google.com or google.co.in.",
    )
    parser.add_argument(
        "--hl",
        default=os.getenv("SERPAPI_HL", DEFAULT_SERPAPI_LANGUAGE),
        help="Google UI language for SerpApi, for example en.",
    )
    parser.add_argument(
        "--gl",
        default=os.getenv("SERPAPI_GL", DEFAULT_SERPAPI_COUNTRY),
        help="Google country code for SerpApi, for example in or us.",
    )

    args = parser.parse_args()
    query, max_profiles = prompt_runtime_settings(args.query, args.max_profiles)
    config = ScraperConfig(
        query=query,
        max_profiles=max_profiles,
        output_base=args.output_base,
        serpapi_api_key=args.api_key.strip(),
        google_domain=args.google_domain.strip() or DEFAULT_SERPAPI_GOOGLE_DOMAIN,
        language=args.hl.strip() or DEFAULT_SERPAPI_LANGUAGE,
        country=args.gl.strip().lower(),
    )
    validate_config(config)
    return config
