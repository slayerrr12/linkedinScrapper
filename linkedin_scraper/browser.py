import os
import platform
import time
from typing import Callable, Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import HTTPError, MaxRetryError, ProtocolError

from .utils import normalize_whitespace


CHALLENGE_URL_FRAGMENTS = (
    "captcha",
    "/checkpoint",
    "/challenge",
    "challengeid",
    "/sorry/",
    "sorry/index",
)
CHALLENGE_TEXT_MARKERS = (
    "verify you are human",
    "security verification",
    "complete the security check",
    "unusual traffic from your computer network",
    "our systems have detected unusual traffic",
    "not a robot",
    "prove you're not a robot",
    "recaptcha",
    "hcaptcha",
)
CHALLENGE_IFRAME_SELECTORS = (
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='captcha']",
    "iframe[title*='CAPTCHA']",
    "iframe[title*='captcha']",
)
NAVIGATION_EXCEPTIONS = (
    ConnectionError,
    OSError,
    TimeoutException,
    WebDriverException,
    HTTPError,
    MaxRetryError,
    ProtocolError,
)


def wait_for_document(driver: webdriver.Chrome, timeout: int = 15) -> None:
    WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script("return document.readyState") == "complete"
    )


def setup_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1600,1200")

    if platform.system() == "Linux":
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def close_driver(driver: Optional[webdriver.Chrome]) -> None:
    if driver is None:
        return

    try:
        driver.quit()
    except Exception:
        pass


def restart_driver(driver: Optional[webdriver.Chrome], headless: bool, reason: str) -> webdriver.Chrome:
    print(f"Restarting Chrome because {reason}.")
    close_driver(driver)
    return setup_driver(headless=headless)


def safe_current_url(driver: webdriver.Chrome) -> str:
    try:
        return driver.current_url or ""
    except WebDriverException:
        return ""


def safe_page_text(driver: webdriver.Chrome) -> str:
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        return normalize_whitespace(body.text).lower()
    except (NoSuchElementException, WebDriverException):
        return ""


def detect_challenge_reason(driver: webdriver.Chrome) -> Optional[str]:
    current_url = safe_current_url(driver).lower()
    if any(fragment in current_url for fragment in CHALLENGE_URL_FRAGMENTS):
        return f"verification page at {current_url}"

    for selector in CHALLENGE_IFRAME_SELECTORS:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return "CAPTCHA iframe detected on the page"
        except WebDriverException:
            continue

    page_text = safe_page_text(driver)
    for marker in CHALLENGE_TEXT_MARKERS:
        if marker in page_text:
            return f"page text indicates verification: '{marker}'"

    return None


def wait_for_manual_challenge_resolution(
    driver: webdriver.Chrome,
    context: str,
    timeout_seconds: int,
    success_condition: Callable[[webdriver.Chrome], bool],
) -> bool:
    print(f"{context} requires manual verification in the Chrome window.")
    print(f"Solve it in the browser. Waiting up to {timeout_seconds} seconds before timing out.")

    deadline = time.time() + timeout_seconds
    last_reason: Optional[str] = None

    while time.time() < deadline:
        if success_condition(driver):
            print(f"{context} verification cleared. Resuming.")
            return True

        reason = detect_challenge_reason(driver)
        if reason and reason != last_reason:
            print(f"  Waiting on manual verification: {reason}")
            last_reason = reason
        elif not reason and last_reason:
            print("  Verification page looks cleared. Checking whether the run can continue...")
            last_reason = None

        time.sleep(2)

    print(f"{context} timed out after {timeout_seconds} seconds while waiting for manual verification.")
    return False


def ensure_verification_cleared(
    driver: webdriver.Chrome,
    context: str,
    timeout_seconds: int,
    headless: bool,
) -> bool:
    challenge_reason = detect_challenge_reason(driver)
    if not challenge_reason:
        return True

    print(f"{context} triggered a verification step: {challenge_reason}")
    if headless:
        print(f"{context} cannot be resolved manually while running headless. Rerun with --no-headless.")
        return False

    return wait_for_manual_challenge_resolution(
        driver,
        context,
        timeout_seconds,
        lambda current_driver: detect_challenge_reason(current_driver) is None,
    )


def navigate_with_retries(
    driver: webdriver.Chrome,
    url: str,
    context: str,
    headless: bool,
    max_attempts: int = 3,
) -> webdriver.Chrome:
    current_driver = driver
    last_exception: Optional[BaseException] = None

    for attempt in range(1, max_attempts + 1):
        try:
            if attempt > 1:
                print(f"{context}: retrying navigation ({attempt}/{max_attempts})")
            current_driver.get(url)
            wait_for_document(current_driver)
            return current_driver
        except KeyboardInterrupt:
            raise
        except NAVIGATION_EXCEPTIONS as exc:
            last_exception = exc
            print(f"{context}: navigation failed with {exc.__class__.__name__}: {exc}")

            if attempt >= max_attempts:
                break

            time.sleep(min(2 * attempt, 5))
            current_driver = restart_driver(
                current_driver,
                headless,
                f"{context.lower()} failed on attempt {attempt}",
            )

    raise RuntimeError(f"{context} failed after {max_attempts} navigation attempts.") from last_exception
