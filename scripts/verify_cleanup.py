"""
Verify that old flights are being cleaned up properly.
Run: python scripts/verify_cleanup.py

Expected (healthy DB):
- Past flights: 0
- Earliest flight: today or tomorrow
- Latest flight: ~30-60 days from now
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from db_manager import FlightDatabase


def main():
    db = FlightDatabase()
    db.connect()
    cursor = db.conn.cursor()

    # 1. Past flights (should be 0)
    cursor.execute(
        "SELECT COUNT(*) FROM current_prices WHERE departure_date < CURRENT_DATE"
    )
    past_count = cursor.fetchone()[0]

    # 2. Date range
    cursor.execute(
        """
        SELECT MIN(departure_date), MAX(departure_date), COUNT(*)
        FROM current_prices
        """
    )
    min_date, max_date, total = cursor.fetchone()

    cursor.close()
    db.close()

    today = datetime.now().date()
    min_d = min_date if min_date else None
    max_d = max_date if max_date else None

    print("=" * 60)
    print("FlightGrab Cleanup Verification")
    print("=" * 60)
    print(f"Today's date:              {today}")
    print(f"Past flights (departed):   {past_count:,}")
    print(f"Earliest flight:           {min_d}")
    print(f"Latest flight:             {max_d}")
    print(f"Total rows in current_prices: {total:,}")
    print()
    print("Future flights only (departure_date >= today):")
    future = total - past_count if total else 0
    print(f"  {future:,} flights")
    print()

    # Verdict
    if past_count == 0:
        print("[OK] CLEANUP OK: No past flights in database")
    else:
        print("[!!] CLEANUP NEEDED: Found", past_count, "flights that already departed!")
        print("   Run: python -c \"from db_manager import FlightDatabase; from dotenv import load_dotenv; load_dotenv(); db = FlightDatabase(); db.connect(); db.cleanup_old_data(); db.close()\"")
        print("   Or: Add cleanup to your daily scraper (it should run in incremental)")
    print()

    if min_d and max_d:
        days_range = (max_d - min_d).days if hasattr(max_d - min_d, 'days') else 0
        print(f"Date range span: {days_range} days")
        if days_range > 90:
            print("  (Consider limiting to 60-90 days if DB grows too large)")
    print("=" * 60)


if __name__ == "__main__":
    main()
