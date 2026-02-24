"""
Handle authentication with automated or manual CAPTCHA solving.

Flow (auto_login — default):
1. Launch headless browser
2. Navigate to login page
3. Fill in email/password
4. Detect reCAPTCHA sitekey from the page
5. Send CAPTCHA to 2Captcha API, get solution token
6. Inject token and submit form
7. Save session cookies

Fallback (interactive_login):
1. Launch headed browser (visible)
2. Fill credentials, let user solve CAPTCHA manually
3. Save cookies

Test independently:
    python -m scraper.auth login       # auto-login via 2Captcha (falls back to interactive)
    python -m scraper.auth interactive # force interactive login
    python -m scraper.auth check       # check if saved cookies are still valid
"""

import asyncio
import json
import logging
import sys

from playwright.async_api import async_playwright

from config import (
    LOGIN_URL, BASE_URL, COOKIES_PATH, PP_EMAIL, PP_PASSWORD,
    PAGE_TIMEOUT, TWOCAPTCHA_API_KEY,
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def _fill_credentials(page):
    """Fill email and password fields on the login page."""
    email_selectors = [
        'input[name="email"]',
        '#input-email',
        'input[type="email"]',
    ]
    password_selectors = [
        'input[name="password"]',
        '#input-password',
        'input[type="password"]',
    ]

    for sel in email_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.fill(PP_EMAIL)
                logger.info("Email filled")
                break
        except Exception:
            continue

    for sel in password_selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.fill(PP_PASSWORD)
                logger.info("Password filled")
                break
        except Exception:
            continue


async def _detect_recaptcha_sitekey(page) -> str | None:
    """Find reCAPTCHA v2 sitekey from the page."""
    try:
        sitekey = await page.evaluate("""
            () => {
                // Check for grecaptcha widget
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');
                // Check for iframe
                const iframe = document.querySelector('iframe[src*="recaptcha"]');
                if (iframe) {
                    const m = iframe.src.match(/[?&]k=([^&]+)/);
                    if (m) return m[1];
                }
                // Check for script
                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                for (const s of scripts) {
                    const m = s.src.match(/[?&]render=([^&]+)/);
                    if (m && m[1] !== 'explicit') return m[1];
                }
                return null;
            }
        """)
        return sitekey
    except Exception as e:
        logger.debug("Sitekey detection failed: %s", e)
        return None


async def auto_login() -> list[dict]:
    """
    Automated login using 2Captcha to solve reCAPTCHA.
    Returns list of cookies on success, empty list on failure.
    """
    if not TWOCAPTCHA_API_KEY:
        logger.warning("TWOCAPTCHA_API_KEY not set — cannot auto-login")
        return []

    try:
        from twocaptcha import TwoCaptcha
    except ImportError:
        logger.warning("2captcha-python not installed. Run: pip install 2captcha-python")
        return []

    logger.info("Starting auto-login via 2Captcha...")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        try:
            await page.goto(LOGIN_URL, timeout=PAGE_TIMEOUT)
            await page.wait_for_load_state("networkidle")
        except Exception as e:
            logger.error("Failed to load login page: %s", e)
            await browser.close()
            return []

        # Fill credentials
        await _fill_credentials(page)

        # Detect reCAPTCHA sitekey
        sitekey = await _detect_recaptcha_sitekey(page)
        if not sitekey:
            logger.warning("No reCAPTCHA sitekey found on page — trying to submit without CAPTCHA")
            # Maybe there's no CAPTCHA; try clicking submit directly
            try:
                submit = page.locator('button[type="submit"], input[type="submit"]').first
                await submit.click()
                await page.wait_for_url(
                    lambda url: "route=account/login" not in url,
                    timeout=15_000,
                )
                cookies = await context.cookies()
                await browser.close()
                save_cookies(cookies)
                logger.info("Login successful without CAPTCHA")
                return cookies
            except Exception:
                logger.warning("Submit without CAPTCHA failed")
                await browser.close()
                return []

        logger.info("Found reCAPTCHA sitekey: %s", sitekey[:20] + "...")

        # Solve CAPTCHA via 2Captcha (synchronous call — run in thread)
        solver = TwoCaptcha(TWOCAPTCHA_API_KEY)
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: solver.recaptcha(sitekey=sitekey, url=LOGIN_URL),
            )
            token = result["code"]
            logger.info("2Captcha solved successfully")
        except Exception as e:
            logger.error("2Captcha failed: %s", e)
            await browser.close()
            return []

        # Inject token into the page
        try:
            await page.evaluate(f"""
                () => {{
                    // Set textarea
                    const ta = document.querySelector('#g-recaptcha-response, [name="g-recaptcha-response"]');
                    if (ta) {{
                        ta.style.display = 'block';
                        ta.value = '{token}';
                    }}
                    // Try callback if available
                    if (typeof grecaptcha !== 'undefined') {{
                        try {{ grecaptcha.getResponse = () => '{token}'; }} catch(e) {{}}
                    }}
                }}
            """)
        except Exception as e:
            logger.warning("Token injection warning (non-fatal): %s", e)

        # Submit the form
        try:
            submit = page.locator('button[type="submit"], input[type="submit"]').first
            await submit.click()
            await page.wait_for_url(
                lambda url: "route=account/login" not in url and "login" not in url.split("/")[-1],
                timeout=30_000,
            )
            logger.info("Auto-login successful! URL: %s", page.url)
        except Exception as e:
            logger.error("Login submission failed: %s", e)
            await browser.close()
            return []

        cookies = await context.cookies()
        await browser.close()

    save_cookies(cookies)
    logger.info("Saved %d cookies to %s", len(cookies), COOKIES_PATH)
    return cookies


async def interactive_login() -> list[dict]:
    """
    Open a visible browser, fill credentials, let user solve CAPTCHA.
    Returns list of cookies.
    """
    logger.info("Starting interactive login. A browser window will open.")
    logger.info("Please solve the CAPTCHA manually, then wait for login to complete.")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        await page.goto(LOGIN_URL, timeout=PAGE_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # Fill in credentials
        await _fill_credentials(page)

        logger.info("=" * 60)
        logger.info("SOLVE THE CAPTCHA in the browser window, then click Login.")
        logger.info("Waiting for successful login (URL change or account page)...")
        logger.info("=" * 60)

        # Wait for navigation away from login page (max 5 minutes for CAPTCHA)
        try:
            await page.wait_for_url(
                lambda url: "route=account/login" not in url and "login" not in url.split("/")[-1],
                timeout=300_000,
            )
            logger.info("Login successful! Current URL: %s", page.url)
        except Exception:
            logger.error("Login timed out or failed. Current URL: %s", page.url)
            await browser.close()
            return []

        # Get cookies
        cookies = await context.cookies()
        await browser.close()

    # Save cookies
    save_cookies(cookies)
    logger.info("Saved %d cookies to %s", len(cookies), COOKIES_PATH)
    return cookies


def save_cookies(cookies: list[dict]):
    """Save cookies to JSON file."""
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Convert to serializable format
    serializable = []
    for c in cookies:
        entry = {k: v for k, v in c.items() if isinstance(v, (str, int, float, bool))}
        serializable.append(entry)
    COOKIES_PATH.write_text(json.dumps(serializable, indent=2))


def load_cookies() -> list[dict] | None:
    """Load cookies from file if they exist."""
    if not COOKIES_PATH.exists():
        logger.warning("No saved cookies found at %s", COOKIES_PATH)
        return None
    try:
        cookies = json.loads(COOKIES_PATH.read_text())
        logger.info("Loaded %d cookies from file", len(cookies))
        return cookies
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load cookies: %s", e)
        return None


async def check_session_valid(cookies: list[dict] | None = None) -> bool:
    """Check if the saved/given cookies provide an authenticated session."""
    if cookies is None:
        cookies = load_cookies()
    if not cookies:
        return False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(cookies)
        page = await context.new_page()

        try:
            # Try to access account page
            await page.goto(
                f"{BASE_URL}/index.php?route=account/account",
                timeout=PAGE_TIMEOUT,
            )
            await page.wait_for_load_state("networkidle")

            # If redirected to login, session is invalid
            current_url = page.url
            is_valid = "route=account/login" not in current_url
            if is_valid:
                logger.info("Session is valid (account page accessible)")
            else:
                logger.warning("Session expired (redirected to login)")
        except Exception as e:
            logger.error("Session check failed: %s", e)
            is_valid = False
        finally:
            await browser.close()

    return is_valid


async def ensure_authenticated() -> list[dict] | None:
    """
    Ensure we have valid cookies.
    1. Try saved cookies
    2. Try auto-login (2Captcha)
    3. Fall back to interactive login
    Returns cookies or None if all methods failed.
    """
    cookies = load_cookies()
    if cookies and await check_session_valid(cookies):
        return cookies

    logger.info("Need to re-authenticate...")

    # Try auto-login first
    cookies = await auto_login()
    if cookies and await check_session_valid(cookies):
        return cookies

    # Fall back to interactive
    logger.info("Auto-login failed. Falling back to interactive login...")
    cookies = await interactive_login()
    return cookies if cookies else None


async def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    action = sys.argv[1] if len(sys.argv) > 1 else "login"

    if action == "login":
        # Try auto first, fall back to interactive
        cookies = await auto_login()
        if not cookies:
            logger.info("Auto-login unavailable. Starting interactive login...")
            cookies = await interactive_login()
        if cookies:
            logger.info("Login complete. %d cookies saved.", len(cookies))
        else:
            logger.error("Login failed.")
    elif action == "interactive":
        cookies = await interactive_login()
        if cookies:
            logger.info("Login complete. %d cookies saved.", len(cookies))
        else:
            logger.error("Login failed.")
    elif action == "check":
        valid = await check_session_valid()
        logger.info("Session valid: %s", valid)
    else:
        logger.error("Unknown action: %s. Use 'login', 'interactive', or 'check'.", action)


if __name__ == "__main__":
    asyncio.run(run())
