"""
Link Extractor – Google Cloud Run service
Accepts a Google Flights booking URL, clicks Continue, returns the airline redirect URL.
Or accepts a search URL, clicks Select flight -> Continue, returns the airline redirect URL.
"""

import re
from urllib.parse import urlparse

from fastapi import FastAPI, Query, HTTPException
from playwright.async_api import async_playwright

app = FastAPI(title="FlightGrab Link Extractor")

# Consent cookies to reduce "Before you continue" gates
_CONSENT_COOKIES = [
    {"name": "CONSENT", "value": "YES+cb.20210328-17-p0.en+FX+667", "domain": ".google.com", "path": "/"},
    {"name": "SOCS", "value": "CAISHAgCEhJnd3NfMjAyNTAxMDctMF9SQzEaAmVuIAEaBgiA8t23Bg", "domain": ".google.com", "path": "/"},
]


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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/extract")
async def extract_link(
    url: str = Query(..., description="Google Flights booking URL (google.com/travel/flights/booking/...)"),
    timeout_ms: int = Query(25000, ge=5000, le=60000),
):
    """
    Navigate to the Google Flights booking page, click Continue,
    and return the final airline/OTA redirect URL.
    """
    if not url or "google.com/travel/flights/booking" not in url:
        raise HTTPException(status_code=400, detail="Invalid URL: must be a Google Flights booking link")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu",
                "--disable-extensions", "--no-first-run", "--disable-background-networking",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1200)

            btns = page.locator("button[aria-label*='Continue to book with' i]")
            n = await btns.count()
            if n == 0:
                btns = page.locator("button:has-text('Continue')")
                n = await btns.count()
            if n == 0:
                await browser.close()
                return {"success": False, "error": "No Continue button found", "fallback_url": url}

            pages_before = set(page.context.pages)
            await btns.nth(0).click()
            await page.wait_for_timeout(1000)

            pages_after = set(page.context.pages)
            new_pages = pages_after - pages_before
            target = next(iter(new_pages), page)

            for _ in range(15):
                await page.wait_for_timeout(300)
                final_url = target.url
                if final_url and _is_external_link(final_url):
                    await browser.close()
                    return {"success": True, "url": final_url}

            final_url = target.url
            await browser.close()
            if final_url and _is_external_link(final_url):
                return {"success": True, "url": final_url}
            return {"success": False, "error": "No external redirect captured", "fallback_url": url}

        except Exception as e:
            await browser.close()
            return {"success": False, "error": str(e), "fallback_url": url}


@app.get("/extract-from-search")
async def extract_from_search(
    url: str = Query(..., description="Google Flights search URL (?q=... or tfs param)"),
    timeout_ms: int = Query(45000, ge=15000, le=90000),
):
    """
    Full flow: open search page -> click Select flight -> booking page -> click Continue -> return airline URL.
    Use when you only have the search URL (e.g. from Daily Scraper).
    """
    if not url or "google.com/travel/flights" not in url:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL: must be a Google Flights search or booking link",
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu",
                "--disable-extensions", "--no-first-run", "--disable-background-networking",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        )
        await context.add_cookies(_CONSENT_COOKIES)
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(1200)

            # If we land on booking page (direct booking URL), skip Select flight
            if "/travel/flights/booking" in page.url:
                booking_url = page.url
            else:
                # Search page: click first "Select flight"
                select_locators = [
                    page.locator("li.pIav2d button[aria-label*='Select flight' i]"),
                    page.locator("button[aria-label*='Select flight' i]"),
                    page.locator("button:has-text('Select flight')"),
                ]
                clicked = False
                for loc in select_locators:
                    try:
                        if await loc.count() > 0:
                            async with page.expect_navigation(url=re.compile(r".*travel/flights.*"), timeout=15000):
                                await loc.nth(0).evaluate("el => el.click()")
                            clicked = True
                            break
                    except Exception:
                        try:
                            async with context.expect_page(timeout=5000) as np:
                                await loc.nth(0).evaluate("el => el.click()")
                            page = await np.value
                            clicked = True
                            break
                        except Exception:
                            continue
                if not clicked:
                    await browser.close()
                    return {"success": False, "error": "No Select flight button found", "fallback_url": url}

                await page.wait_for_load_state("domcontentloaded", timeout=12000)
                await page.wait_for_timeout(1000)

                if "/travel/flights/booking" not in page.url:
                    try:
                        await page.wait_for_url(re.compile(r".*/travel/flights/booking.*"), timeout=15000)
                    except Exception:
                        pass

                booking_url = page.url
                if "/travel/flights/booking" not in booking_url:
                    await browser.close()
                    return {"success": False, "error": "Did not reach booking page", "fallback_url": url}

            # Booking page: click Continue to book with (same as /extract)
            await page.wait_for_timeout(1000)
            btns = page.locator("button[aria-label*='Continue to book with' i]")
            n = await btns.count()
            if n == 0:
                btns = page.locator("button:has-text('Continue')")
                n = await btns.count()
            if n == 0:
                await browser.close()
                return {"success": False, "error": "No Continue button on booking page", "fallback_url": url}

            pages_before = set(page.context.pages)
            await btns.nth(0).click()
            await page.wait_for_timeout(1000)

            pages_after = set(page.context.pages)
            new_pages = pages_after - pages_before
            target = next(iter(new_pages), page)

            for _ in range(15):
                await page.wait_for_timeout(300)
                final_url = target.url
                if final_url and _is_external_link(final_url):
                    await browser.close()
                    return {"success": True, "url": final_url}

            final_url = target.url
            await browser.close()
            if final_url and _is_external_link(final_url):
                return {"success": True, "url": final_url}
            return {"success": False, "error": "No external redirect captured", "fallback_url": url}

        except Exception as e:
            await browser.close()
            return {"success": False, "error": str(e), "fallback_url": url}
