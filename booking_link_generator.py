"""
Real-time booking link generator: simulates clicking "Continue" on Google Flights
to get a fresh OTA redirect (tokens expire, so we regenerate on user click).
"""

import asyncio
import logging
from urllib.parse import urlparse

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


def _is_external_link(href: str) -> bool:
    if not href:
        return False
    try:
        u = urlparse(href)
        if u.scheme not in ("http", "https"):
            return False
        host = (u.netloc or "").lower()
        if host.endswith("google.com") or host.endswith("googleusercontent.com") or host.endswith("gstatic.com"):
            return False
        return True
    except Exception:
        return False


class BookingLinkGenerator:
    """Generates fresh OTA booking links by clicking Continue on Google Flights."""

    def __init__(self, headless: bool = True):
        self._playwright = None
        self._browser = None
        self._context = None
        self._headless = headless

    async def start(self):
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-GB",
            java_script_enabled=True,
        )
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        try:
            from reverse_engineering_scraping.consent_utils import seed_google_consent
            await seed_google_consent(self._context)
        except ImportError:
            pass

    async def get_fresh_booking_link(self, google_booking_url: str, timeout_ms: int = 20000) -> str | None:
        """
        Navigate to Google Flights booking page, click first Continue, capture OTA redirect.
        Returns final airline URL or None (fallback to google_booking_url).
        """
        if not google_booking_url or "google.com/travel/flights/booking" not in google_booking_url:
            return None

        await self.start()
        page = None
        try:
            page = await self._context.new_page()
            page.set_default_timeout(timeout_ms)

            await page.goto(google_booking_url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(3000)

            try:
                from reverse_engineering_scraping.consent_utils import handle_google_consent_any_frame
                if await handle_google_consent_any_frame(page, timeout_ms=5000, accept=True):
                    await page.goto(google_booking_url, wait_until="networkidle", timeout=20000)
                    await page.wait_for_timeout(3000)
            except ImportError:
                pass

            try:
                await page.wait_for_selector(
                    "button[aria-label*='Continue to book with' i]",
                    timeout=15000,
                    state="visible",
                )
            except Exception:
                pass

            btns = page.locator("button[aria-label*='Continue to book with' i]")
            n = await btns.count()
            if n == 0:
                try:
                    btns = page.locator("button:has-text('Continue')")
                    n = await btns.count()
                except Exception:
                    pass
            if n == 0:
                logger.warning("No Continue button found")
                return None

            pages_before = set(page.context.pages)
            await btns.nth(0).evaluate("el => el.click()")

            target = page
            await asyncio.sleep(1.5)
            pages_after = set(page.context.pages)
            new_pages = pages_after - pages_before
            if new_pages:
                target = next(iter(new_pages))

            for _ in range(20):
                await asyncio.sleep(0.5)
                url = target.url
                if url and _is_external_link(url):
                    if target != page:
                        try:
                            await target.close()
                        except Exception:
                            pass
                    logger.info("Generated fresh link: %s...", url[:80])
                    return url

            final = target.url
            if target != page:
                try:
                    await target.close()
                except Exception:
                    pass
            return final if final and _is_external_link(final) else None

        except Exception as e:
            logger.warning("Booking link generation failed: %s", e)
            return None
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._playwright = None


_generator: BookingLinkGenerator | None = None


async def get_generator() -> BookingLinkGenerator:
    global _generator
    if _generator is None:
        _generator = BookingLinkGenerator()
        await _generator.start()
    return _generator


async def close_generator():
    global _generator
    if _generator:
        await _generator.close()
        _generator = None
