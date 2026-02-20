"""
Download city/destination images from Pixabay using landmark-specific searches.
Ensures geographically accurate images (e.g. "burj khalifa dubai" not generic skyline).

Setup:
  1. Get free API key from https://pixabay.com/api/docs/
  2. Add to .env: PIXABAY_API_KEY=your_key_here

Run:
  python scripts/fetch_city_images.py              # fetch international cities
  python scripts/fetch_city_images.py --all        # also try airports without landmark mapping
"""
import os
import sys
import urllib.request
import urllib.parse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from scripts.city_image_sources import LANDMARK_SEARCHES, AIRPORT_TO_COUNTRY

SCRIPT_DIR = Path(__file__).parent
OUT_DIR = SCRIPT_DIR.parent / "static" / "images" / "airports"


def download_image(url: str, filepath: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FlightGrab/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def fetch_pixabay_image(api_key: str, search: str) -> str | None:
    """Search Pixabay and return the best image URL, or None."""
    q = urllib.parse.quote(search)
    url = f"https://pixabay.com/api/?key={api_key}&q={q}&image_type=photo&safesearch=true&per_page=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FlightGrab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        hits = data.get("hits", [])
        if not hits:
            return None
        hit = hits[0]
        return hit.get("webformatURL") or hit.get("largeImageURL")
    except Exception as e:
        print(f"  API error: {e}")
        return None


def main():
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        print("Set PIXABAY_API_KEY in .env (free at https://pixabay.com/api/docs/)")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    to_fetch = list(LANDMARK_SEARCHES.items())

    for airport, search in to_fetch:
        filepath = OUT_DIR / f"{airport}.jpg"
        if filepath.exists():
            print(f"{airport}: already exists, skip (delete to re-fetch)")
            continue
        print(f"{airport}: searching Pixabay for '{search}'...")
        img_url = fetch_pixabay_image(api_key, search)
        if img_url:
            if download_image(img_url, filepath):
                print(f"  Saved {filepath}")
            else:
                print(f"  Download failed")
        else:
            print(f"  No results. Try manually: https://pixabay.com/images/search/{urllib.parse.quote(search)}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
