"""
One-time migration: drop old current_prices table so create_tables creates
the new rolling 30-day schema (departure_date, first_seen, last_updated).

Run from project root:
  python -m dotenv run python scripts/migrate_to_rolling_window.py

Or with DATABASE_URL set:
  python scripts/migrate_to_rolling_window.py
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

from dotenv import load_dotenv
load_dotenv()

from db_manager import FlightDatabase

def main():
    db = FlightDatabase()
    db.connect()
    cur = db.conn.cursor()
    cur.execute("DROP TABLE IF EXISTS current_prices CASCADE;")
    db.conn.commit()
    cur.close()
    print("✓ Dropped old current_prices table")
    db.create_tables()
    db.close()
    print("✓ New rolling 30-day schema ready. Run: python daily_scraper.py baseline")

if __name__ == "__main__":
    main()
