"""
Daily scraping job – rolling 30-day window.

- Render (512 MB): run incremental only. Baseline = 7 days, low-memory (or delete baseline cron).
- Local (full baseline): set FULL_BASELINE=1 and run baseline → 31 days, multi-worker, ~1–3 hr.
"""

import gc
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from flight_scraper import (
    scrape_all_routes,
    scrape_incremental,
    scrape_routes_sequential,
    TOP_50_US_AIRPORTS,
)
from db_manager import FlightDatabase

# Origins: 5 = test, 50 = full
NUM_ORIGINS = 5
# Incremental: 1 worker for 512 MB (Render). Use more if you have RAM.
NUM_WORKERS = 1

# Full baseline (local): set FULL_BASELINE=1 → 31 days, multi-worker
FULL_BASELINE = os.environ.get("FULL_BASELINE", "").lower() in ("1", "true", "yes")
FULL_BASELINE_WORKERS = 5
FULL_BASELINE_DAYS = 31

# Low-memory baseline (Render / no FULL_BASELINE): 7 days, sequential
BASELINE_DAYS = 7
BASELINE_BATCH_SIZE = 10


def _route_tuples_for_day(origins, destinations, departure_date):
    """List of (origin, dest, date) for one day."""
    out = []
    for o in origins:
        for d in destinations:
            if o != d:
                out.append((o, d, departure_date))
    return out


def run_baseline_scrape():
    """
    BASELINE:
    - FULL_BASELINE=1 (local): 31 days, multi-worker, insert per day. ~1–3 hr for 5 origins.
    - Otherwise (Render): 7 days, sequential, small batches. Fits 512 MB.
    """
    if FULL_BASELINE:
        _run_baseline_full()
    else:
        _run_baseline_low_memory()


def _run_baseline_full():
    """Full 31-day baseline with multiple workers. Run locally with FULL_BASELINE=1."""
    print("=" * 60)
    print(f"BASELINE (FULL) - 31 days, {FULL_BASELINE_WORKERS} workers - {datetime.now()}")
    print("=" * 60)

    db = FlightDatabase()
    db.connect()
    db.create_tables()

    origins = TOP_50_US_AIRPORTS[:NUM_ORIGINS]
    total = 0
    for days_ahead in range(0, FULL_BASELINE_DAYS):
        departure_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        print(f"\nDay {days_ahead + 1}/{FULL_BASELINE_DAYS}: {departure_date}")
        flights = scrape_all_routes(
            origins, TOP_50_US_AIRPORTS, departure_date, num_workers=FULL_BASELINE_WORKERS
        )
        if flights:
            db.insert_flights(flights)
            total += len(flights)
        gc.collect()

    if total:
        db.create_daily_snapshot()
        print(f"\n✓ Full baseline completed: {total} flights ({FULL_BASELINE_DAYS} days)")
    else:
        print("\n✗ No results collected")
        sys.exit(1)
    db.close()


def _run_baseline_low_memory():
    """7-day baseline, sequential, small batches. For Render 512 MB."""
    print("=" * 60)
    print(f"BASELINE (low-memory, 7 days) - {datetime.now()}")
    print("=" * 60)

    db = FlightDatabase()
    db.connect()
    db.create_tables()

    origins = TOP_50_US_AIRPORTS[:NUM_ORIGINS]
    total = 0
    for days_ahead in range(0, BASELINE_DAYS):
        departure_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        routes = _route_tuples_for_day(origins, TOP_50_US_AIRPORTS, departure_date)
        print(f"\nDay {days_ahead + 1}/{BASELINE_DAYS}: {departure_date} ({len(routes)} routes)")

        batch = []
        for flight in scrape_routes_sequential(routes):
            batch.append(flight)
            if len(batch) >= BASELINE_BATCH_SIZE:
                db.insert_flights(batch)
                total += len(batch)
                batch.clear()
                gc.collect()
        if batch:
            db.insert_flights(batch)
            total += len(batch)
            batch.clear()
        gc.collect()

    if total:
        db.create_daily_snapshot()
        print(f"\n✓ Baseline completed: {total} flights ({BASELINE_DAYS} days)")
    else:
        print("\n✗ No results collected")
        sys.exit(1)
    db.close()


def run_incremental_scrape():
    """
    DAILY INCREMENTAL – refresh today + add new +30 day.
    Uses 1 worker to stay under 512 MB.
    """
    print("=" * 60)
    print(f"INCREMENTAL SCRAPE - {datetime.now()}")
    print("=" * 60)

    db = FlightDatabase()
    db.connect()
    db.create_tables()

    origins = TOP_50_US_AIRPORTS[:NUM_ORIGINS]
    results = scrape_incremental(
        origins=origins,
        destinations=TOP_50_US_AIRPORTS,
        num_workers=NUM_WORKERS  # 1 = low memory
    )

    if results:
        db.reconnect()  # fresh connection after long scrape (avoids SSL connection closed)
        db.insert_flights(results)
        db.create_daily_snapshot()
        db.cleanup_old_data()
        print(f"\n✓ Incremental completed: {len(results)} flights updated")
    else:
        print("\n✗ No results collected")
        sys.exit(1)
    db.close()


if __name__ == "__main__":
    mode = (sys.argv[1] or "incremental").strip().lower()

    if mode == "baseline":
        print("Running BASELINE (first-time setup)")
        run_baseline_scrape()
    elif mode == "incremental":
        print("Running INCREMENTAL (daily refresh)")
        run_incremental_scrape()
    else:
        print("Usage: python daily_scraper.py [baseline|incremental]")
        print("  baseline    - First time. Set FULL_BASELINE=1 for full 31 days (run locally).")
        print("  incremental - Daily: refresh today + new +30 day")
        print("")
        print("Local full baseline:  FULL_BASELINE=1 python daily_scraper.py baseline")
        print("Render / low-memory:  python daily_scraper.py baseline  (7 days)")
        sys.exit(1)
