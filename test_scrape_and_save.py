"""
Test: Scrape a few routes and save to Neon DB.
Use this to populate sample data for the FlightGrab UI.
"""

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from flight_scraper import scrape_all_routes
from db_manager import FlightDatabase

# Same idea as daily_scraper: days from today for departure date
DAYS_OUT = 14

TEST_ORIGINS = ['JFK', 'LAX', 'ATL']
TEST_DESTINATIONS = ['MIA', 'ORD', 'SFO', 'DEN', 'BOS']
SCRAPE_DATE = (datetime.now() + timedelta(days=DAYS_OUT)).strftime('%Y-%m-%d')

if __name__ == "__main__":
    print("Test scrape: saving to Neon DB...")
    print(f"Date: {SCRAPE_DATE}")
    print(f"Routes: {len(TEST_ORIGINS)} x {len(TEST_DESTINATIONS)} (excluding same airport)\n")

    results = scrape_all_routes(
        TEST_ORIGINS,
        TEST_DESTINATIONS,
        SCRAPE_DATE,
        num_workers=2
    )

    if results:
        db = FlightDatabase()
        db.connect()
        db.create_tables()
        db.insert_flights(results)
        db.close()
        print(f"\nDone. {len(results)} flights saved. Run the app and browse deals from JFK, LAX, or ATL.")
    else:
        print("No results. Check fast-flights and network.")
