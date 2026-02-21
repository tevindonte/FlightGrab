"""
Download city/airport images - no API approval needed.
Uses Wikipedia API (free, no key) + optional Pexels (instant signup at pexels.com/api).

Run:
  python scripts/download_city_images.py           # Wikipedia only (no signup)
  python scripts/download_city_images.py --force   # Re-download existing
  python scripts/download_city_images.py --missing # Only airports without images

Set PEXELS_API_KEY in .env for better quality (optional, instant approval at pexels.com/api).
"""

import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

# Airport code -> Wikipedia page title (city/country for image lookup)
# Use specific city names for best results
AIRPORT_TO_WIKI = {
    # US
    "ATL": "Atlanta", "LAX": "Los Angeles", "ORD": "Chicago", "DFW": "Dallas",
    "DEN": "Denver", "JFK": "New York City", "LGA": "New York City", "EWR": "Newark, New Jersey",
    "SFO": "San Francisco", "SEA": "Seattle", "LAS": "Las Vegas", "MIA": "Miami",
    "MCO": "Orlando, Florida", "PHX": "Phoenix, Arizona", "IAH": "Houston",
    "CLT": "Charlotte, North Carolina", "MSP": "Minneapolis", "DTW": "Detroit",
    "BOS": "Boston", "PHL": "Philadelphia", "SLC": "Salt Lake City", "BWI": "Baltimore",
    "TPA": "Tampa, Florida", "SAN": "San Diego", "PDX": "Portland, Oregon",
    "STL": "St. Louis", "AUS": "Austin, Texas", "BNA": "Nashville, Tennessee",
    "DCA": "Washington, D.C.", "IAD": "Washington, D.C.", "DAL": "Dallas",
    "RDU": "Raleigh", "HOU": "Houston", "SJC": "San Jose, California",
    "MCI": "Kansas City, Missouri", "OAK": "Oakland, California", "SAT": "San Antonio",
    "RSW": "Fort Myers, Florida", "IND": "Indianapolis", "CMH": "Columbus, Ohio",
    "CVG": "Cincinnati", "PIT": "Pittsburgh", "SMF": "Sacramento, California",
    "CLE": "Cleveland", "MKE": "Milwaukee", "SNA": "Santa Ana, California",
    "ANC": "Anchorage, Alaska", "HNL": "Honolulu", "MDW": "Chicago",
    # Middle East
    "DXB": "Dubai", "AUH": "Abu Dhabi", "DOH": "Doha", "BAH": "Manama",
    # Asia
    "SIN": "Singapore", "HKG": "Hong Kong", "NRT": "Tokyo", "HND": "Tokyo",
    "ICN": "Seoul", "BKK": "Bangkok", "KUL": "Kuala Lumpur", "DEL": "New Delhi",
    "BOM": "Mumbai", "DAC": "Dhaka",
    # Europe
    "LHR": "London", "CDG": "Paris", "ORY": "Paris", "FRA": "Frankfurt",
    "AMS": "Amsterdam", "BCN": "Barcelona", "MAD": "Madrid", "FCO": "Rome",
    "DUB": "Dublin", "EDI": "Edinburgh", "MUC": "Munich", "ZRH": "Zurich",
    "VIE": "Vienna", "ATH": "Athens", "IST": "Istanbul", "CPH": "Copenhagen",
    "OSL": "Oslo", "ARN": "Stockholm", "PRG": "Prague", "BUD": "Budapest",
    "WAW": "Warsaw", "LIS": "Lisbon", "BRU": "Brussels",
    # Americas
    "YYZ": "Toronto", "YVR": "Vancouver", "YUL": "Montreal", "YTZ": "Toronto",
    "MEX": "Mexico City", "GRU": "São Paulo", "EZE": "Buenos Aires",
    "PTY": "Panama City", "SJO": "San José, Costa Rica",
    # Oceania
    "SYD": "Sydney", "MEL": "Melbourne", "AKL": "Auckland", "BNE": "Brisbane",
    # Africa
    "JNB": "Johannesburg", "CPT": "Cape Town", "CAI": "Cairo",
    # Other
    "TLV": "Tel Aviv",
}


def _wiki_image_url(title: str) -> str | None:
    """Fetch image URL from Wikipedia for a page title."""
    import urllib.parse
    import json

    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages",
        "titles": title,
        "pithumbsize": 800,
    }
    qs = urllib.parse.urlencode(params)
    full_url = f"{url}?{qs}"

    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "FlightGrab/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), None)
        if page and "thumbnail" in page:
            return page["thumbnail"]["source"]
    except Exception:
        pass
    return None


def _pexels_image_url(search_term: str, api_key: str) -> str | None:
    """Fetch image URL from Pexels (instant API signup)."""
    import urllib.parse
    import json

    q = urllib.parse.quote(search_term)
    url = f"https://api.pexels.com/v1/search?query={q}&per_page=1"

    try:
        req = urllib.request.Request(url, headers={"Authorization": api_key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        photos = data.get("photos", [])
        if photos:
            return photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
    except Exception:
        pass
    return None


def _download_image(url: str, filepath: Path) -> bool:
    """Download image from URL to filepath."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FlightGrab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"  Download error: {e}")
        return False


def main():
    force = "--force" in sys.argv
    missing_only = "--missing" in sys.argv
    pexels_key = os.getenv("PEXELS_API_KEY")

    out_dir = Path(__file__).parent.parent / "static" / "images" / "airports"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading city images to {out_dir}")
    if pexels_key:
        print("Using Pexels + Wikipedia (PEXELS_API_KEY set)")
    else:
        print("Using Wikipedia only (set PEXELS_API_KEY for better quality)")
    print("-" * 60)

    success = 0
    failed = []

    for code, wiki_title in AIRPORT_TO_WIKI.items():
        filepath = out_dir / f"{code}.jpg"

        if filepath.exists() and not force:
            if missing_only:
                continue
            print(f"{code}: exists, skip")
            success += 1
            continue

        img_url = None
        if pexels_key:
            img_url = _pexels_image_url(wiki_title, pexels_key)
            if img_url:
                img_url = (img_url, "pexels")
        if not img_url:
            img_url = _wiki_image_url(wiki_title)
            if img_url:
                img_url = (img_url, "wiki")

        if not img_url:
            print(f"{code}: no image found for '{wiki_title}'")
            failed.append(code)
            continue

        url = img_url[0] if isinstance(img_url, tuple) else img_url
        src = img_url[1] if isinstance(img_url, tuple) else "unknown"
        print(f"{code}: downloading from {src}...", end=" ")
        if _download_image(url, filepath):
            print("OK")
            success += 1
        else:
            failed.append(code)
            print("FAILED")

        time.sleep(0.5 if pexels_key else 1.0)

    print("-" * 60)
    print(f"Downloaded {success}/{len(AIRPORT_TO_WIKI)} images")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print(f"\nImages: {out_dir}")
    print("\nFrontend uses /static/images/airports/{code}.jpg (local first, then state/flag fallback)")


if __name__ == "__main__":
    main()
