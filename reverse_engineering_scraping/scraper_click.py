"""
Click-through scraper: open search URL -> click "Select flight" -> extract booking options from booking page.

DOM structure (from reverse engineering):
- Search page: Two lists - "Top flights" and "Other flights" (depending on Best/Cheapest sort)
- Flight items: <li class="pIav2d"> inside <ul class="Rk10dc" role="list">
- Select button: button[aria-label="Select flight"] inside each li
- Booking page: Partner cards with "Continue to book with {Partner} for {price}" - buttons trigger JS navigation
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import pandas as pd
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeoutError

try:
    from .consent_utils import seed_google_consent, handle_google_consent_any_frame
except ImportError:
    from consent_utils import seed_google_consent, handle_google_consent_any_frame


@dataclass
class ClickedResult:
    ts: str
    job_index: int
    item_index: int
    job_url: str
    detail_url: str
    title: str
    ok: bool
    error: Optional[str]
    external_links_count: int
    external_links: str
    internal_links_count: int
    internal_links: str
    booking_options: str  # "Partner | Price" pairs
    booking_urls: str  # "Partner | Price | URL" triples from clicking Continue


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


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


def _dedupe_preserve(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


# "Continue to book with Flightnetwork for 417 US dollars" or "Continue to book with China Eastern airline"
_CONTINUE_WITH_PRICE = re.compile(
    r"Continue to book with (.+?)\s+for\s+([\d,$]+)\s*(?:US dollars)?",
    re.I,
)
_CONTINUE_NO_PRICE = re.compile(r"Continue to book with (.+)", re.I)


async def _extract_booking_options(page: Page) -> str:
    """Extract Partner | Price from Continue buttons on booking page."""
    parts = []
    seen = set()
    try:
        btns = page.locator("button[aria-label*='Continue to book with' i]")
        n = min(await btns.count(), 50)
        for i in range(n):
            label = (await btns.nth(i).get_attribute("aria-label")) or ""
            partner, price = None, None
            m = _CONTINUE_WITH_PRICE.search(label)
            if m:
                partner = _norm_ws(m.group(1))
                price = _norm_ws(m.group(2))
            else:
                m2 = _CONTINUE_NO_PRICE.search(label)
                if m2:
                    partner = _norm_ws(m2.group(1))
                    price = "?"
            key = (partner or "", price or "")
            if partner and key not in seen:
                seen.add(key)
                parts.append(f"{partner} | {price}" if price else partner)
    except Exception:
        pass
    return " | ".join(parts) if parts else ""


async def _capture_booking_urls_via_click(page: Page, booking_page_url: str) -> str:
    """
    Click each Continue button, wait for redirect to OTA, capture final URL, go back.
    Handles both same-tab navigation and new-tab (popup) - Continue may open
    google.com/travel/clk which redirects to the OTA (e.g. singaporeair.com).
    Returns "Partner | Price | URL" triples separated by " || ".
    """
    captured = []
    max_buttons = 5  # limit round-trips
    context = page.context

    try:
        btns = page.locator("button[aria-label*='Continue to book with' i]")
        n = min(await btns.count(), max_buttons)
        for i in range(n):
            try:
                label = (await btns.nth(i).get_attribute("aria-label")) or ""
                partner, price = None, "?"
                m = _CONTINUE_WITH_PRICE.search(label)
                if m:
                    partner = _norm_ws(m.group(1))
                    price = _norm_ws(m.group(2))
                else:
                    m2 = _CONTINUE_NO_PRICE.search(label)
                    if m2:
                        partner = _norm_ws(m2.group(1))
                if not partner:
                    continue

                pages_before = set(context.pages)
                await btns.nth(i).evaluate("el => el.click()")

                # Determine target: new tab (popup) or same tab
                target = page
                await asyncio.sleep(1.5)
                pages_after = set(context.pages)
                new_pages = pages_after - pages_before
                if new_pages:
                    target = next(iter(new_pages))

                try:
                    await target.wait_for_load_state("domcontentloaded", timeout=10000)
                    for _ in range(16):
                        await asyncio.sleep(0.5)
                        url = target.url
                        if url and _is_external_link(url):
                            break
                except Exception:
                    await asyncio.sleep(4)

                final_url = target.url
                if target != page:
                    try:
                        await target.close()
                    except Exception:
                        pass

                if final_url and _is_external_link(final_url):
                    captured.append(f"{partner} | {price} | {final_url}")
                else:
                    captured.append(f"{partner} | {price} | (redirect failed)")

                await page.goto(booking_page_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
                btns = page.locator("button[aria-label*='Continue to book with' i]")
            except Exception:
                try:
                    await page.goto(booking_page_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500)
                    btns = page.locator("button[aria-label*='Continue to book with' i]")
                except Exception:
                    break
    except Exception:
        pass
    return " || ".join(captured) if captured else ""


async def _looks_like_consent(page: Page) -> bool:
    try:
        title = (await page.title()) or ""
    except Exception:
        title = ""
    if "before you continue" in title.lower():
        return True
    try:
        body = await page.locator("body").inner_text(timeout=2000)
        b = body.lower()
        return ("before you continue" in b) or ("we use cookies" in b)
    except Exception:
        return False


async def scrape_one_search_click_results(
    page: Page,
    job_url: str,
    job_index: int,
    max_items: int = 5,
    timeout_ms: int = 45000,
    accept_cookies: bool = True,
) -> List[ClickedResult]:
    out: List[ClickedResult] = []

    def fail_row(msg: str) -> ClickedResult:
        return ClickedResult(
            ts=_now_iso(),
            job_index=job_index,
            item_index=-1,
            job_url=job_url,
            detail_url=page.url if page else job_url,
            title="__SEARCH_PAGE_FAILED__",
            ok=False,
            error=msg,
            external_links_count=0,
            external_links="",
            internal_links_count=0,
            internal_links="",
            booking_options="",
            booking_urls="",
        )

    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(1500)

        handled = await handle_google_consent_any_frame(page, timeout_ms=timeout_ms, accept=accept_cookies)
        if handled:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(2000)

        if await _looks_like_consent(page):
            out.append(fail_row("consent_gate_still_present"))
            return out

        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)

        # Flight items: li.pIav2d inside ul.Rk10dc (Top flights + Other flights)
        # Each li has button[aria-label="Select flight"]
        candidates = [
            page.locator("li.pIav2d button[aria-label*='Select flight' i]"),
            page.locator("ul.Rk10dc li.pIav2d button[aria-label*='Select flight' i]"),
            page.get_by_role("button", name=re.compile(r"Select flight", re.I)),
            page.locator("button:has-text('Select flight')"),
            page.locator("[aria-label*='Select flight' i]"),
        ]

        buttons = None
        btn_count = 0
        for loc in candidates:
            try:
                c = await loc.count()
                if c > 0:
                    buttons = loc
                    btn_count = c
                    break
            except Exception:
                continue

        if not buttons or btn_count == 0:
            title = (await page.title()) or ""
            body_snip = ""
            try:
                body_snip = _norm_ws(await page.locator("body").inner_text(timeout=5000))[:400]
            except Exception:
                pass
            out.append(fail_row(f"no_select_flight_buttons_found | title={title!r} | body_snip={body_snip!r}"))
            return out

        click_n = min(btn_count, max_items)

        for i in range(click_n):
            buttons = None
            btn_count = 0
            for loc in candidates:
                try:
                    c = await loc.count()
                    if c > 0:
                        buttons = loc
                        btn_count = c
                        break
                except Exception:
                    continue
            if not buttons or btn_count == 0:
                break

            btn = buttons.nth(i)

            async def _do_click():
                """Click via JS to bypass visibility checks (e.g. element in collapsed section)."""
                await btn.evaluate("el => el.click()")

            detail_page: Page = page
            opened_new_tab = False

            try:
                async with page.expect_navigation(url=re.compile(r".*travel/flights.*"), timeout=15000):
                    await _do_click()
                detail_page = page
                await detail_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            except Exception:
                try:
                    async with page.context.expect_page(timeout=3500) as newp:
                        await _do_click()
                    detail_page = await newp.value
                    opened_new_tab = True
                    await detail_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                except Exception:
                    await _do_click()
                    detail_page = page
                    try:
                        await detail_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                    except Exception:
                        pass

            await handle_google_consent_any_frame(detail_page, timeout_ms=timeout_ms, accept=accept_cookies)
            try:
                await detail_page.wait_for_url(re.compile(r".*/travel/flights/booking.*"), timeout=20000)
            except Exception:
                pass

            detail_url = detail_page.url
            try:
                title = await detail_page.title()
            except Exception:
                title = "__DETAIL__"

            links = []
            try:
                anchors = detail_page.locator("a[href]")
                n = min(await anchors.count(), 500)
                for k in range(n):
                    href = (await anchors.nth(k).get_attribute("href")) or ""
                    href = href.strip()
                    if not href:
                        continue
                    href = urljoin(detail_url, href)
                    links.append(href)
            except Exception:
                pass

            links = _dedupe_preserve(links)
            external = [u for u in links if _is_external_link(u)]
            internal = [u for u in links if u and not _is_external_link(u)]

            booking_opts = ""
            booking_urls_str = ""
            if "/travel/flights/booking" in detail_url:
                await detail_page.wait_for_timeout(2000)  # wait for booking options to load
                booking_opts = await _extract_booking_options(detail_page)
                booking_urls_str = await _capture_booking_urls_via_click(detail_page, detail_url)

            out.append(
                ClickedResult(
                    ts=_now_iso(),
                    job_index=job_index,
                    item_index=i,
                    job_url=job_url,
                    detail_url=detail_url,
                    title=title or "__DETAIL__",
                    ok=True,
                    error=None,
                    external_links_count=len(external),
                    external_links=" | ".join(external),
                    internal_links_count=len(internal),
                    internal_links=" | ".join(internal),
                    booking_options=booking_opts,
                    booking_urls=booking_urls_str,
                )
            )

            if opened_new_tab and detail_page is not page:
                try:
                    await detail_page.close()
                except Exception:
                    pass
                await page.wait_for_timeout(800)
            else:
                try:
                    await page.go_back(wait_until="domcontentloaded")
                except Exception:
                    await page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(1500)

        return out

    except Exception as e:
        out.append(fail_row(f"{type(e).__name__}: {e}"))
        return out


async def run_click_scraper(
    jobs_df: pd.DataFrame,
    concurrency: int = 2,
    headless: bool = True,
    timeout_ms: int = 45000,
    max_items_per_search: int = 5,
    accept_cookies: bool = True,
    user_data_dir: str = "/tmp/gflights_profile_click",
    seed_consent_cookies: bool = True,
    output_path: Optional[str] = None,
) -> pd.DataFrame:
    jobs = jobs_df.to_dict(orient="records")
    sem = asyncio.Semaphore(concurrency)
    results: List[ClickedResult] = []

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            locale="en-GB",
            timezone_id="Europe/London",
            viewport={"width": 1280, "height": 900},
        )
        context.set_default_timeout(timeout_ms)

        if seed_consent_cookies:
            await seed_google_consent(context)

        async def worker(job_idx: int, job: Dict[str, Any]):
            async with sem:
                page = await context.new_page()
                try:
                    url = str(job.get("url", "")).strip()
                    if not url:
                        return []
                    return await scrape_one_search_click_results(
                        page=page,
                        job_url=url,
                        job_index=job_idx,
                        max_items=max_items_per_search,
                        timeout_ms=timeout_ms,
                        accept_cookies=accept_cookies,
                    )
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

        tasks = [asyncio.create_task(worker(i, jobs[i])) for i in range(len(jobs))]
        for coro in asyncio.as_completed(tasks):
            rows = await coro
            results.extend(rows)

        await context.close()

    df = pd.DataFrame([asdict(r) for r in results])
    if output_path:
        df.to_csv(output_path, index=False)
    return df
