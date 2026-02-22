"""
Add manually requested flight routes. Scrapes real prices, inserts to DB, downloads images.

Usage:
  python scripts/add_manual_routes.py
  python scripts/add_manual_routes.py --days 14    # Scrape 14 days ahead (default 7)
  python scripts/add_manual_routes.py --no-scrape  # Skip scrape, only download images

Requires: DATABASE_URL in .env. Uses fast-flights for scraping.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

# Routes to add: (origin, destination) - will scrape both directions
MANUAL_ROUTES = [
    ("LAX", "CDG"),   # Los Angeles <-> Paris
    ("JFK", "CDG"),   # New York <-> Paris
]

# Airports that may need images downloaded (non-US often need city images)
AIRPORTS_TO_IMAGE = ["CDG"]


def download_airport_images(codes: list[str]) -> None:
    """Download images for airports that don't have them."""
    scripts_dir = Path(__file__).parent
    project_root = scripts_dir.parent
    out_dir = project_root / "static" / "images" / "airports"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Import from download_city_images (run from project root: python scripts/add_manual_routes.py)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "download_city_images", scripts_dir / "download_city_images.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    AIRPORT_TO_WIKI = mod.AIRPORT_TO_WIKI
    _wiki_image_url = mod._wiki_image_url
    _pexels_image_url = mod._pexels_image_url
    _download_image = mod._download_image

    pexels_key = os.getenv("PEXELS_API_KEY")
    for code in codes:
        if code not in AIRPORT_TO_WIKI:
            print(f"  {code}: no Wikipedia mapping, skip image")
            continue
        filepath = out_dir / f"{code}.jpg"
        if filepath.exists():
            print(f"  {code}: image exists, skip")
            continue

        wiki_title = AIRPORT_TO_WIKI[code]
        img_url = None
        if pexels_key:
            img_url = _pexels_image_url(wiki_title, pexels_key)
            if img_url:
                img_url = (img_url, "pexels")
        if not img_url:
            u = _wiki_image_url(wiki_title)
            if u:
                img_url = (u, "wiki")
        if not img_url:
            print(f"  {code}: no image found for '{wiki_title}'")
            continue

        url = img_url[0] if isinstance(img_url, tuple) else img_url
        src = img_url[1] if isinstance(img_url, tuple) else "unknown"
        print(f"  {code}: downloading from {src}...", end=" ")
        if _download_image(url, filepath):
            print("OK")
        else:
            print("FAILED")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Add manual routes: LAX-CDG, JFK-CDG")
    ap.add_argument("--days", type=int, default=7, help="Days to scrape (default 7)")
    ap.add_argument("--start-date", default=None, help="Start date YYYY-MM-DD (default: today)")
    ap.add_argument("--no-scrape", action="store_true", help="Skip scrape, only download images")
    args = ap.parse_args()

    print("=" * 60)
    print("MANUAL ROUTES: LAX-CDG, JFK-CDG (both directions)")
    print("=" * 60)

    # 1. Download images for airports that need them
    print("\n1. Checking airport images...")
    download_airport_images(AIRPORTS_TO_IMAGE)

    if args.no_scrape:
        print("\n--no-scrape: skipping scrape. Done.")
        return

    # 2. Build route list (both directions)
    all_routes = []
    for o, d in MANUAL_ROUTES:
        all_routes.append((o, d))
        all_routes.append((d, o))

    # 3. Scrape for each date
    from flight_scraper import scrape_route

    if args.start_date:
        try:
            start = datetime.strptime(args.start_date, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid --start-date {args.start_date!r}, use YYYY-MM-DD")
            sys.exit(1)
    else:
        start = datetime.now()

    dates_to_scrape = []
    for i in range(args.days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        dates_to_scrape.append(d)

    print(f"  Dates: {dates_to_scrape[0]} to {dates_to_scrape[-1]}")

    print(f"\n2. Scraping {len(all_routes)} routes x {len(dates_to_scrape)} dates...")
    flights = []
    for (origin, dest) in all_routes:
        for date in dates_to_scrape:
            result = scrape_route((origin, dest, date))
            if result:
                flights.append(result)
                print(f"   {origin}-{dest} {date}: ${result['price']}")
            else:
                print(f"   {origin}-{dest} {date}: no results")

    # Filter invalid prices
    flights = [f for f in flights if f.get("price") and float(f.get("price", 0) or 0) > 0]
    if not flights:
        print("\nNo valid flights scraped. Check network and fast-flights.")
        sys.exit(1)

    # 4. Fetch booking URLs for a subset (optional, requires Playwright + playwright install)
    try:
        from booking_url_fetcher import fetch_booking_urls, merge_booking_urls_into_flights
        urls = fetch_booking_urls(flights, max_routes=min(20, len(flights)))
        merge_booking_urls_into_flights(flights, urls)
        print(f"\n3. Fetched google_booking_url for {len(urls)} routes")
    except ImportError:
        print("\n3. Playwright not available, skipping booking URL fetch")
    except Exception as e:
        print(f"\n3. Booking URL fetch skipped: {str(e)[:80]}...")

    # 5. Insert to DB
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\nDATABASE_URL not set. Cannot insert to DB.")
        print("Flights scraped:", len(flights))
        sys.exit(1)

    from db_manager import FlightDatabase

    db = FlightDatabase()
    db.connect()
    db.create_tables()
    db.insert_flights(flights)
    db.create_daily_snapshot()
    db.close()

    print(f"\nDone. Inserted {len(flights)} flights.")
    print("  Routes: LAX-CDG, CDG-LAX, JFK-CDG, CDG-JFK")
    print("  Select LAX or JFK as origin to see Paris (CDG) deals.")


if __name__ == "__main__":
    main()
