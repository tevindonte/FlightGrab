"""
Basic search page scrape: open URL, extract price text, handle consent.
GBP forcing via hl=en-GB&gl=GB&curr=GBP.
"""

import ast
import asyncio
import re
from datetime import datetime, timezone

import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from .consent_utils import handle_google_consent_any_frame
except ImportError:
    from consent_utils import handle_google_consent_any_frame

GBP_QUERY = "hl=en-GB&gl=GB&curr=GBP"


def force_gbp(url: str) -> str:
    if not url:
        return url
    if "curr=GBP" in url:
        return url
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{GBP_QUERY}"


def parse_airports_cell(x):
    if x is None:
        return []
    try:
        if pd.isna(x):
            return []
    except Exception:
        pass
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                v = ast.literal_eval(s)
                if isinstance(v, list):
                    return v
            except Exception:
                pass
        return re.findall(r"[A-Z0-9]{3}", s.upper())
    return []


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _extract_from_text(text: str) -> str | None:
    text = _norm_ws(text)
    m = re.search(r"\bfrom\s+([£$€]\s?\d[\d,]*(?:\.\d{2})?)\b", text, flags=re.IGNORECASE)
    if m:
        return f"from {m.group(1)}"
    return None


def _extract_any_money(text: str) -> str | None:
    text = _norm_ws(text)
    m = re.search(r"\b([£$€]\s?\d[\d,]*(?:\.\d{2})?)\b", text)
    return m.group(1) if m else None


async def extract_top_departing_flight_block(page) -> dict:
    out = {"top_flight_text": None, "top_flight_price": None}
    try:
        header = page.locator("text=/Top departing flights/i").first
        if await header.count() == 0:
            return out
        container = header.locator("xpath=ancestor::div[1]")
        txt = await container.inner_text(timeout=4000)
        txt = _norm_ws(txt)
        if len(txt) < 80:
            container2 = header.locator("xpath=ancestor::div[2]")
            txt2 = await container2.inner_text(timeout=4000)
            if len(_norm_ws(txt2)) > len(txt):
                txt = _norm_ws(txt2)
        out["top_flight_text"] = txt[:800]
        out["top_flight_price"] = _extract_any_money(txt)
    except Exception:
        pass
    return out


async def scrape_search(page, job: dict) -> dict:
    url = force_gbp(job["url"])
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "origin": job.get("origin"),
        "dest": job.get("dest"),
        "dest_label": job.get("dest_label"),
        "depart_date": job.get("depart_date"),
        "return_date": job.get("return_date"),
        "trip_type": job.get("trip_type"),
        "url": url,
        "ok": False,
        "error": None,
        "title": None,
        "from_price": None,
        "any_price": None,
        "top_flight_price": None,
        "top_flight_text": None,
    }
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(1200)
        handled = await handle_google_consent_any_frame(page, timeout_ms=20000, accept=True)
        if handled:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(1500)
        result["title"] = await page.title()
        if (result["title"] or "").lower().strip() == "before you continue":
            result["error"] = "consent_gate_still_present"
            return result
        try:
            candidates = page.locator("text=/\\bfrom\\b/i")
            n = min(await candidates.count(), 30)
            for i in range(n):
                try:
                    t = await candidates.nth(i).inner_text(timeout=1500)
                    fp = _extract_from_text(t)
                    if fp:
                        result["from_price"] = fp
                        break
                except Exception:
                    continue
        except Exception:
            pass
        if not result["from_price"] or not result["any_price"]:
            try:
                body_text = await page.locator("body").inner_text(timeout=20000)
            except Exception:
                body_text = ""
            if not result["from_price"]:
                result["from_price"] = _extract_from_text(body_text)
            if not result["any_price"]:
                result["any_price"] = _extract_any_money(body_text)
        top = await extract_top_departing_flight_block(page)
        result.update(top)
        result["ok"] = True
    except PlaywrightTimeoutError as e:
        result["error"] = f"timeout: {e}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


async def run_scraper(
    jobs_df: pd.DataFrame,
    headless: bool = True,
    concurrency: int = 3,
    user_data_dir: str | None = "/tmp/gflights_profile",
) -> pd.DataFrame:
    jobs = jobs_df.to_dict(orient="records")
    sem = asyncio.Semaphore(concurrency)
    results = []
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            locale="en-GB",
            timezone_id="Europe/London",
            viewport={"width": 1280, "height": 900},
        )
        async def worker(job):
            async with sem:
                page = await context.new_page()
                try:
                    return await scrape_search(page, job)
                finally:
                    await page.close()
        try:
            tasks = [asyncio.create_task(worker(job)) for job in jobs]
            for coro in asyncio.as_completed(tasks):
                r = await coro
                results.append(r)
        finally:
            await context.close()
    return pd.DataFrame(results)


async def main_async(
    jobs_csv: str = "bulk_search_jobs.csv",
    out_csv: str = "scrape_results.csv",
    headless: bool = True,
    concurrency: int = 3,
    limit: int | None = None,
    user_data_dir: str | None = "/tmp/gflights_profile",
) -> pd.DataFrame:
    jobs_df = pd.read_csv(jobs_csv)
    jobs_df["url"] = jobs_df["url"].astype(str).apply(force_gbp)
    if limit is not None:
        jobs_df = jobs_df.head(int(limit)).copy()
    out_df = await run_scraper(
        jobs_df, headless=headless, concurrency=concurrency, user_data_dir=user_data_dir
    )
    out_df.to_csv(out_csv, index=False)
    print(f"Saved: {out_csv}")
    return out_df


def run_main_sync(**kwargs):
    return asyncio.run(main_async(**kwargs))
