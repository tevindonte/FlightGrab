"""
Fetch google_booking_url for routes by opening search page and clicking "Select flight".
Used by Daily Scraper to populate booking URLs for a subset of routes (time-limited).
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse

from playwright.async_api import async_playwright

_CONSENT_COOKIES = [
    {"name": "CONSENT", "value": "YES+cb.20210328-17-p0.en+FX+667", "domain": ".google.com", "path": "/"},
    {"name": "SOCS", "value": "CAISHAgCEhJnd3NfMjAyNTAxMDctMF9SQzEaAmVuIAEaBgiA8t23Bg", "domain": ".google.com", "path": "/"},
]


def _search_url(origin: str, destination: str, date: str) -> str:
    q = f"Flights from {origin} to {destination} on {date}"
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"


async def _fetch_one(
    page,
    search_url: str,
    timeout_ms: int = 30000,
) -> str | None:
    """Open search URL, click first Select flight, return booking page URL or None."""
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)

        select_locators = [
            page.locator("li.pIav2d button[aria-label*='Select flight' i]"),
            page.locator("button[aria-label*='Select flight' i]"),
            page.locator("button:has-text('Select flight')"),
        ]
        for loc in select_locators:
            try:
                if await loc.count() > 0:
                    async with page.expect_navigation(url=re.compile(r".*travel/flights.*"), timeout=15000):
                        await loc.nth(0).evaluate("el => el.click()")
                    break
            except Exception:
                try:
                    async with page.context.expect_page(timeout=4000) as np:
                        await loc.nth(0).evaluate("el => el.click()")
                    new_page = await np.value
                    await new_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                    detail_url = new_page.url
                    await new_page.close()
                    if "/travel/flights/booking" in detail_url:
                        return detail_url
                    return None
                except Exception:
                    continue
        else:
            return None

        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_url(re.compile(r".*/travel/flights/booking.*"), timeout=15000)
        except Exception:
            pass

        url = page.url
        if "/travel/flights/booking" in url:
            return url
        return None
    except Exception:
        return None


def fetch_booking_urls(
    flights: list[dict],
    max_routes: int = 20,
    timeout_ms: int = 30000,
) -> dict[tuple[str, str, str], str]:
    """
    For each of the first max_routes flights, open search page, click Select flight,
    capture booking URL. Returns {(origin, dest, date): google_booking_url}.
    """
    if not flights or max_routes <= 0:
        return {}

    routes = []
    for f in flights[:max_routes]:
        o = (f.get("origin") or "").strip().upper()
        d = (f.get("destination") or "").strip().upper()
        dt = f.get("departure_date") or ""
        if o and d and dt:
            routes.append((o, d, dt))

    if not routes:
        return {}

    results: dict[tuple[str, str, str], str] = {}

    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            )
            await context.add_cookies(_CONSENT_COOKIES)
            context.set_default_timeout(timeout_ms)

            page = await context.new_page()

            for origin, dest, date in routes:
                search_url = _search_url(origin, dest, date)
                detail_url = await _fetch_one(page, search_url, timeout_ms)
                if detail_url:
                    results[(origin, dest, date)] = detail_url

                # Brief pause between routes
                await page.wait_for_timeout(500)

            await browser.close()

    asyncio.run(run())
    return results


def merge_booking_urls_into_flights(
    flights: list[dict],
    booking_urls: dict[tuple[str, str, str], str],
) -> None:
    """In-place: set google_booking_url on flight dicts that have a match."""
    for f in flights:
        key = (
            (f.get("origin") or "").strip().upper(),
            (f.get("destination") or "").strip().upper(),
            (f.get("departure_date") or "").strip(),
        )
        if key in booking_urls:
            f["google_booking_url"] = booking_urls[key]
