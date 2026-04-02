from urllib.parse import parse_qs, urlparse

import requests

from .config import ScraperConfig


SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
SERPAPI_PAGE_SIZE = 10


def normalize_linkedin_profile_url(raw_url: str) -> str | None:
    if not raw_url:
        return None

    parsed = urlparse(raw_url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{raw_url.lstrip('/')}")

    hostname = parsed.netloc.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    if hostname != "linkedin.com" and not hostname.endswith(".linkedin.com"):
        return None

    if not parsed.path.startswith("/in/"):
        return None

    clean_path = parsed.path.rstrip("/")
    return f"https://www.linkedin.com{clean_path}"


def extract_next_start(payload: dict, fallback_start: int, result_count: int) -> int | None:
    next_url = (payload.get("serpapi_pagination") or {}).get("next")
    if next_url:
        parsed = urlparse(next_url)
        next_values = parse_qs(parsed.query).get("start")
        if next_values:
            try:
                return int(next_values[0])
            except ValueError:
                pass

    if result_count <= 0:
        return None

    return fallback_start + result_count


def fetch_serpapi_page(config: ScraperConfig, google_query: str, start: int) -> dict:
    params = {
        "engine": "google",
        "q": google_query,
        "api_key": config.serpapi_api_key,
        "google_domain": config.google_domain,
        "hl": config.language,
        "start": start,
        "num": SERPAPI_PAGE_SIZE,
    }
    if config.country:
        params["gl"] = config.country

    response = requests.get(SERPAPI_ENDPOINT, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()

    error_message = payload.get("error")
    if error_message:
        raise RuntimeError(f"SerpApi error: {error_message}")

    return payload


def search_linkedin_profile_links(config: ScraperConfig) -> list[str]:
    google_query = f"site:linkedin.com/in {config.query}"
    print(f"Searching SerpApi for LinkedIn profile links: {google_query}")

    linkedin_urls: list[str] = []
    start = 0

    while len(linkedin_urls) < config.max_profiles:
        payload = fetch_serpapi_page(config, google_query, start)
        organic_results = payload.get("organic_results") or []
        if not organic_results:
            break

        print(f"\nScanning SerpApi page starting at result {start + 1}")
        for result in organic_results:
            normalized_url = normalize_linkedin_profile_url(result.get("link", ""))
            if normalized_url and normalized_url not in linkedin_urls:
                linkedin_urls.append(normalized_url)
                print(f"  + {normalized_url}")
                if len(linkedin_urls) >= config.max_profiles:
                    break

        if len(linkedin_urls) >= config.max_profiles:
            break

        next_start = extract_next_start(payload, start, len(organic_results))
        if next_start is None or next_start <= start:
            break
        start = next_start

    print(f"\nFound {len(linkedin_urls)} unique LinkedIn profile links.")
    return linkedin_urls
