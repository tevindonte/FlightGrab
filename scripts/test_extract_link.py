"""
Test Cloud Run link extraction - verify the returned airline URL works.
Run locally to test before adding batch refresh.

Usage:
  python scripts/test_extract_link.py LAX CDG 2026-03-15
  python scripts/test_extract_link.py JFK CDG 2026-03-15 --open   # Opens URL in browser
  python scripts/test_extract_link.py LAX CDG 2026-03-15 --url URL  # Use custom Cloud Run URL
  python scripts/test_extract_link.py LAX CDG 2026-03-15 --tfs     # Use tfs (protobuf) URL format

Set CLOUD_RUN_URL or LINK_EXTRACTOR_URL in .env, or pass --url https://link-extractor-xxx.run.app
"""

import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()


def main():
    if len(sys.argv) < 4:
        print("Usage: python scripts/test_extract_link.py ORIGIN DEST DATE [--open] [--url CLOUD_RUN_URL]")
        print("  e.g. python scripts/test_extract_link.py LAX CDG 2026-03-15 --open")
        sys.exit(1)

    origin = sys.argv[1].upper()
    dest = sys.argv[2].upper()
    date = sys.argv[3]

    open_browser = "--open" in sys.argv
    url_idx = sys.argv.index("--url") + 1 if "--url" in sys.argv else None
    cloud_run_url = sys.argv[url_idx] if url_idx and url_idx < len(sys.argv) else None

    if not cloud_run_url:
        cloud_run_url = (os.getenv("CLOUD_RUN_URL") or os.getenv("LINK_EXTRACTOR_URL") or "").strip().rstrip("/")

    if not cloud_run_url:
        print("Set CLOUD_RUN_URL in .env or pass --url https://link-extractor-xxx.run.app")
        sys.exit(1)

    use_tfs = "--tfs" in sys.argv
    if use_tfs:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "reverse_engineering_scraping"))
            from tfs_encoder import build_flights_url_from_iata
            fallback = build_flights_url_from_iata(
                slices_iata=[(date, origin, dest)],
                adults=1, cabin="economy", trip_type="one_way", sort="cheapest",
            )
            print("Using tfs (protobuf) URL format")
        except Exception as e:
            print(f"tfs URL failed: {e}, falling back to ?q= format")
            fallback = (
                "https://www.google.com/travel/flights?q="
                + quote(f"Flights from {origin} to {dest} on {date}")
            )
    else:
        fallback = (
            "https://www.google.com/travel/flights?q="
            + quote(f"Flights from {origin} to {dest} on {date}")
        )

    print(f"Testing: {origin} -> {dest} on {date}")
    print(f"Cloud Run: {cloud_run_url}")
    print(f"Using extract-from-search (search -> Select -> Continue)...")
    print("This may take 30-60 seconds...")
    print()

    try:
        try:
            import httpx
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(
                    f"{cloud_run_url}/extract-from-search",
                    params={"url": fallback},
                )
                data = resp.json()
        except ImportError:
            import urllib.request
            import json
            req_url = f"{cloud_run_url}/extract-from-search?url={quote(fallback)}"
            req = urllib.request.Request(req_url, headers={"User-Agent": "FlightGrab/1.0"})
            with urllib.request.urlopen(req, timeout=65) as resp:
                data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if data.get("success") and data.get("url"):
        airline_url = data["url"]
        print("SUCCESS - Extracted airline URL:")
        print(airline_url)
        if open_browser:
            print("\nOpening in browser...")
            webbrowser.open(airline_url)
    else:
        print("FAILED - Cloud Run could not extract link")
        print(f"  Error: {data.get('error', 'unknown')}")
        print(f"  Fallback: {fallback}")
        if open_browser:
            print("\nOpening fallback (Google Flights) in browser...")
            webbrowser.open(fallback)


if __name__ == "__main__":
    main()
