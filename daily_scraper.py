"""
Daily scraping job – rolling 30-day window.
Run baseline ONCE, then incremental daily (cron).
"""

import sys
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from flight_scraper import scrape_baseline, scrape_incremental, TOP_50_US_AIRPORTS
from db_manager import FlightDatabase

# Phase: 5 = test (~1 hr baseline), 10 = medium (~2 hr), 50 = full (~9 hr)
NUM_ORIGINS = 50
NUM_WORKERS = 5


def run_baseline_scrape():
    """
    INITIAL BASELINE – run ONCE to populate the 30-day window.
    WARNING: 5 origins × 50 dests × 31 dates ≈ 7,750 routes (~1 hour).
    Set NUM_ORIGINS = 50 for full run (~9 hours).
    """
    print("=" * 60)
    print(f"BASELINE SCRAPE - {datetime.now()}")
    print("=" * 60)

    db = FlightDatabase()
    db.connect()
    db.create_tables()

    origins = TOP_50_US_AIRPORTS[:NUM_ORIGINS]
    results = scrape_baseline(
        origins=origins,
        destinations=TOP_50_US_AIRPORTS,
        num_workers=NUM_WORKERS
    )

    if results:
        db.insert_flights(results)
        db.create_daily_snapshot()
        print(f"\n✓ Baseline completed: {len(results)} flights")
    else:
        print("\n✗ No results collected")
        sys.exit(1)
    db.close()


def run_incremental_scrape():
    """
    DAILY INCREMENTAL – refresh today + add new +30 day.
    ~5,000 routes for 5 origins (~3.5 min), ~34 min for 50 origins.
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
        num_workers=NUM_WORKERS
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
        print("  baseline    - First time: scrape next 31 days (~1 hr for 5 origins)")
        print("  incremental - Daily: refresh today + new +30 day (~3.5 min for 5 origins)")
        sys.exit(1)
