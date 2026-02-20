"""
Full pipeline: build jobs → run click scraper → save to DB.
Uses country_top_airports, popular explore destinations, paired routes (A→B and B→A).
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(BASE)
for p in [BASE, PARENT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv()

from db_manager import FlightDatabase

try:
    from full_job_builder import build_full_jobs
    from scraper_click import run_click_scraper
except ImportError:
    from reverse_engineering_scraping.full_job_builder import build_full_jobs
    from reverse_engineering_scraping.scraper_click import run_click_scraper


def _parse_price_from_booking(booking_str: str) -> float | None:
    """Parse first price from 'Partner | $455' or 'Partner | 455'."""
    if not booking_str:
        return None
    for part in booking_str.split("|"):
        part = part.strip()
        m = re.search(r"[\d,]+\.?\d*", part.replace(",", ""))
        if m:
            try:
                return float(m.group().replace(",", ""))
            except (ValueError, TypeError):
                continue
    return None


def _parse_first_booking_url(booking_urls_str: str) -> str | None:
    """Extract first OTA URL from 'Partner | Price | URL || ...'."""
    if not booking_urls_str:
        return None
    for triple in booking_urls_str.split("||"):
        parts = [p.strip() for p in triple.split("|")]
        if len(parts) >= 3 and parts[2].startswith("http") and "(redirect failed)" not in parts[2]:
            return parts[2]
    return None


def click_results_to_flights(results_df: pd.DataFrame, jobs_df: pd.DataFrame) -> list[dict]:
    """
    Transform ClickedResult rows + jobs into DB flight rows.
    One row per (origin, dest, date) - take best (lowest price) per job.
    """
    jobs = jobs_df.to_dict(orient="records")
    flights = []

    for _, row in results_df.iterrows():
        if not row.get("ok"):
            continue
        job_idx = int(row.get("job_index", -1))
        if job_idx < 0 or job_idx >= len(jobs):
            continue
        job = jobs[job_idx]
        origin = str(job.get("origin", "")).strip().upper()
        dest = str(job.get("dest", "")).strip().upper()
        depart_date = job.get("depart_date")
        if not origin or not dest or not depart_date:
            continue

        price = _parse_price_from_booking(row.get("booking_options") or "")
        if price is None:
            price = _parse_price_from_booking(row.get("booking_urls") or "")
        if price is None or price <= 0:
            continue

        booking_url = _parse_first_booking_url(row.get("booking_urls") or "")
        if not booking_url:
            booking_url = row.get("detail_url") or job.get("url", "")
        google_booking_url = row.get("detail_url") or ""
        job_url = row.get("job_url") or job.get("url", "")

        flights.append({
            "origin": origin,
            "destination": dest,
            "route": f"{origin}-{dest}",
            "departure_date": depart_date,
            "price": price,
            "currency": "USD",
            "airline": None,
            "departure_time": None,
            "arrival_time": None,
            "duration": None,
            "num_stops": 0,
            "is_best": False,
            "google_flights_url": job_url,
            "booking_url": booking_url,
            "google_booking_url": google_booking_url,
            "first_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })

    return flights


def run_pipeline(
    mode: str = "popular",
    depart_date: str | None = None,
    top_origins_per_country: int = 3,
    max_countries: int | None = 5,
    max_popular_destinations: int = 15,
    max_jobs: int | None = 50,
    max_jobs_per_run: int | None = None,
    worker_id: int | None = None,
    total_workers: int | None = None,
    max_items_per_search: int = 1,
    concurrency: int = 2,
    headless: bool = True,
    user_data_dir: str | None = None,
    output_csv: str | None = None,
    save_to_db: bool = True,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Build jobs → scrape → transform → optional DB save.
    When worker_id and total_workers are set (e.g. from env), shards jobs across workers.
    Returns (results_df, flights_list).
    """
    if user_data_dir is None:
        base_tmp = os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp"))
        worker_suffix = f"_w{worker_id}" if worker_id is not None else ""
        user_data_dir = os.path.join(base_tmp, f"gflights_full_pipeline{worker_suffix}")

    print("Building jobs...")
    jobs_df = build_full_jobs(
        mode=mode,
        depart_date=depart_date,
        top_origins_per_country=top_origins_per_country,
        max_countries=max_countries,
        max_popular_destinations=max_popular_destinations,
    )

    if worker_id is not None and total_workers is not None and total_workers > 1:
        idx = worker_id % total_workers
        jobs_df = jobs_df.iloc[idx::total_workers].reset_index(drop=True)
        print(f"  Worker {idx + 1}/{total_workers}: shard has {len(jobs_df)} jobs")

    if max_jobs:
        jobs_df = jobs_df.head(max_jobs)
    if max_jobs_per_run and len(jobs_df) > max_jobs_per_run:
        jobs_df = jobs_df.head(max_jobs_per_run)
    print(f"  Jobs: {len(jobs_df)}")

    print("Running click scraper...")
    import asyncio
    results_df = asyncio.run(
        run_click_scraper(
            jobs_df,
            concurrency=concurrency,
            headless=headless,
            max_items_per_search=max_items_per_search,
            user_data_dir=user_data_dir,
            output_path=output_csv,
        )
    )
    ok_count = int((results_df["ok"] == True).sum())
    print(f"  OK: {ok_count}/{len(results_df)}")

    flights = click_results_to_flights(results_df, jobs_df)
    print(f"  Flights to save: {len(flights)}")

    if save_to_db and flights:
        db = FlightDatabase()
        db.connect()
        db.create_tables()
        db.insert_flights(flights)
        db.close()
        print("  Saved to DB")

    return results_df, flights


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Full scrape pipeline: jobs → scrape → DB")
    ap.add_argument("--mode", default="popular", choices=["popular", "all"])
    ap.add_argument("--max-countries", type=int, default=None, help="Limit countries (default: all)")
    ap.add_argument("--max-jobs", type=int, default=None, help="Cap total jobs (before sharding)")
    ap.add_argument("--max-jobs-per-run", type=int, default=None, help="Cap jobs per run (for CI timeout)")
    ap.add_argument("--worker-id", type=int, default=None, help="Worker index (0-based) when distributed")
    ap.add_argument("--total-workers", type=int, default=None, help="Total workers for sharding")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--headed", action="store_true", help="Run browser visible")
    ap.add_argument("--no-db", action="store_true", help="Skip DB save")
    ap.add_argument("--output", default=None, help="Save click results CSV path")
    args = ap.parse_args()

    worker_id = args.worker_id
    total_workers = args.total_workers
    if worker_id is None and os.environ.get("WORKER_ID"):
        try:
            worker_id = int(os.environ["WORKER_ID"]) - 1  # 1-based in env -> 0-based
        except ValueError:
            pass
    elif worker_id is not None and worker_id >= 1:
        worker_id = worker_id - 1  # CLI 1-based -> 0-based for sharding
    if total_workers is None and os.environ.get("TOTAL_WORKERS"):
        try:
            total_workers = int(os.environ["TOTAL_WORKERS"])
        except ValueError:
            pass

    run_pipeline(
        mode=args.mode,
        max_countries=args.max_countries,
        max_jobs=args.max_jobs,
        max_jobs_per_run=args.max_jobs_per_run,
        worker_id=worker_id,
        total_workers=total_workers,
        concurrency=args.concurrency,
        headless=not args.headed,
        save_to_db=not args.no_db,
        output_csv=args.output,
    )
