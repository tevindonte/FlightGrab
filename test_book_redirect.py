"""
Quick test: generate fresh booking link for one route and open in browser.
Run from project root: python test_book_redirect.py
To see the browser (helps with Google detection): python test_book_redirect.py --headed

Uses DUB->AUH 2026-05-21 from your DB as example. Edit origin/dest/date below if needed.
"""

import asyncio
import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from db_manager import FlightDatabase


async def main():
    # Route to test (from your DB - DUB->AUH has google_booking_url)
    origin, destination, date = "DUB", "AUH", "2026-05-21"

    db = FlightDatabase()
    db.connect()
    db.create_tables()
    c = db.conn.cursor()
    try:
        c.execute(
            """
            SELECT COALESCE(google_booking_url, booking_url) as url
            FROM current_prices
            WHERE origin = %s AND destination = %s AND departure_date = %s
            ORDER BY price ASC
            LIMIT 1
            """,
            (origin, destination, date),
        )
        row = c.fetchone()
        url = row[0] if row else None
    except Exception:
        c.execute(
            "SELECT booking_url FROM current_prices WHERE origin = %s AND destination = %s AND departure_date = %s LIMIT 1",
            (origin, destination, date),
        )
        row = c.fetchone()
        url = row[0] if row else None
    if not url or "google.com/travel/flights/booking" not in str(url or ""):
        c.execute(
            """
            SELECT origin, destination, departure_date, booking_url
            FROM current_prices
            WHERE departure_date >= CURRENT_DATE AND booking_url LIKE %s
            ORDER BY last_updated DESC
            LIMIT 1
            """,
            ("%google.com/travel/flights/booking%",),
        )
        fallback = c.fetchone()
        if fallback:
            origin, destination, date = fallback[0], fallback[1], str(fallback[2])
            url = fallback[3]
            print(f"Using first available: {origin}->{destination} ({date})")
    c.close()
    db.close()
    google_booking_url = url if url and "google.com/travel/flights/booking" in str(url) else None
    if not google_booking_url:
        print(f"No Google booking URL for {origin}->{destination} on {date}")
        print("Run the scraper first, or try a route from your DB that has google_booking_url.")
        return
    print(f"Testing: {origin} -> {destination} ({date})")
    print("Loading Google Flights page, clicking Continue, capturing redirect...")

    from booking_link_generator import BookingLinkGenerator
    headed = "--headed" in sys.argv or "-h" in sys.argv
    if headed:
        print("Running with visible browser (--headed)...")
    gen = BookingLinkGenerator(headless=not headed)
    await gen.start()
    try:
        fresh_link = await gen.get_fresh_booking_link(google_booking_url, timeout_ms=25000)
        if fresh_link:
            print(f"\n✓ Fresh link: {fresh_link[:100]}...")
            print("Opening booking page in same browser...")
            page = await gen._context.new_page()
            await page.goto(fresh_link)
            print("Press Enter to close browser...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            await page.close()
        else:
            print("\n✗ Could not capture redirect. Opening Google Flights page instead...")
            page = await gen._context.new_page()
            await page.goto(google_booking_url)
            print("Press Enter to close browser...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            await page.close()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await gen.close()


if __name__ == "__main__":
    asyncio.run(main())
