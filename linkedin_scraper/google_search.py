from typing import Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .browser import (
    ensure_verification_cleared,
    navigate_with_retries,
    safe_current_url,
    wait_for_document,
)


def normalize_linkedin_profile_url(href: str) -> Optional[str]:
    if not href:
        return None

    parsed = urlparse(href)
    if "google." in parsed.netloc and parsed.path == "/url":
        href = parse_qs(parsed.query).get("q", [href])[0]

    href = unquote(href).strip()
    if not href:
        return None

    parsed = urlparse(href)
    if not parsed.scheme:
        parsed = urlparse(f"https://{href.lstrip('/')}")

    hostname = parsed.netloc.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    if hostname != "linkedin.com" and not hostname.endswith(".linkedin.com"):
        return None

    if not parsed.path.startswith("/in/"):
        return None

    clean_path = parsed.path.rstrip("/")
    return f"https://www.linkedin.com{clean_path}"


def find_next_google_page_button(driver: webdriver.Chrome):
    selectors = (
        (By.CSS_SELECTOR, "a#pnnext"),
        (By.CSS_SELECTOR, "a[aria-label='Next page']"),
        (By.XPATH, "//a[contains(., 'Next')]"),
    )
    for by, selector in selectors:
        elements = driver.find_elements(by, selector)
        for element in elements:
            if element.is_displayed():
                return element
    return None


def search_google_for_linkedin_profile_links(
    driver: webdriver.Chrome,
    search_query: str,
    max_results: int,
    headless: bool,
    challenge_timeout: int,
) -> tuple[webdriver.Chrome, list[str]]:
    linkedin_urls: list[str] = []
    google_query = f"site:linkedin.com/in {search_query}"
    google_search_url = f"https://www.google.com/search?q={quote_plus(google_query)}"

    print(f"Searching Google for LinkedIn profile links: {google_query}")
    driver = navigate_with_retries(driver, google_search_url, "Google search", headless)
    if not ensure_verification_cleared(driver, "Google search", challenge_timeout, headless):
        return driver, linkedin_urls

    page_num = 1
    while len(linkedin_urls) < max_results:
        if not ensure_verification_cleared(driver, f"Google search page {page_num}", challenge_timeout, headless):
            break

        print(f"\nScanning Google page {page_num}")
        WebDriverWait(driver, 15).until(lambda current_driver: bool(current_driver.find_elements(By.TAG_NAME, "a")))

        for link in driver.find_elements(By.TAG_NAME, "a"):
            try:
                normalized_url = normalize_linkedin_profile_url(link.get_attribute("href"))
            except WebDriverException:
                continue

            if normalized_url and normalized_url not in linkedin_urls:
                linkedin_urls.append(normalized_url)
                print(f"  + {normalized_url}")
                if len(linkedin_urls) >= max_results:
                    break

        if len(linkedin_urls) >= max_results:
            break

        next_button = find_next_google_page_button(driver)
        if next_button is None:
            print("No more Google result pages were found.")
            break

        current_url = safe_current_url(driver)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
        driver.execute_script("arguments[0].click();", next_button)
        WebDriverWait(driver, 15).until(lambda current_driver: safe_current_url(current_driver) != current_url)
        wait_for_document(driver)

        if not ensure_verification_cleared(driver, f"Google next page {page_num + 1}", challenge_timeout, headless):
            break

        page_num += 1

    print(f"\nFound {len(linkedin_urls)} unique LinkedIn profile links.")
    return driver, linkedin_urls
