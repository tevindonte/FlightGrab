"""
Daily scraping job – rolling 30-day window.
Optimized for 512 MB (Render free tier): no multiprocessing in baseline, small batches, 7-day start.
"""

import gc
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
# Incremental: use 1 worker on 512 MB to avoid OOM
NUM_WORKERS = 1
# Baseline: 7 days only (fits 512 MB). Incremental will extend the window over time.
BASELINE_DAYS = 7
# Insert every N routes; lower = less memory (try 5 or 1 if still OOM on 512 MB)
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
    BASELINE – no Pool, sequential scrape in small batches. Fits 512 MB.
    Scrapes 7 days only; incremental daily runs extend the window.
    """
    print("=" * 60)
    print(f"BASELINE SCRAPE (low-memory) - {datetime.now()}")
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
        for i, flight in enumerate(scrape_routes_sequential(routes)):
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
        print("  baseline    - First time: 7 days, low-memory (~45 min for 5 origins)")
        print("  incremental - Daily: refresh today + new +30 day (~3.5 min for 5 origins)")
        sys.exit(1)
