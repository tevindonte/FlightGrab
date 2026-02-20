"""
Example: full one-way pipeline from destinations to bulk jobs.
Run from reverse_engineering_scraping folder:
  python run_example.py

First install deps: pip install -r requirements.txt
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

try:
    import pandas
    import requests
except ImportError as e:
    print("Missing dependency. Run: pip install -r requirements.txt")
    sys.exit(1)

import pandas as pd

RANKED_PATH = os.path.join(BASE, "airport_ranked.csv")
COUNTRY_TOP_PATH = os.path.join(BASE, "country_top_airports.csv")


def main():
    if not os.path.exists(RANKED_PATH) or not os.path.exists(COUNTRY_TOP_PATH):
        print("Building airport data first...")
        from airport_ranking import load_and_score, build_country_airport_map
        df = load_and_score()
        df.to_csv(RANKED_PATH, index=False)
        country_top = build_country_airport_map(df, topk=15, min_routes=10, ensure_one=True)
        country_top.to_csv(COUNTRY_TOP_PATH, index=False)
        print("Saved airport data.")
    else:
        df = pd.read_csv(RANKED_PATH)
        country_top = pd.read_csv(COUNTRY_TOP_PATH)

    from destination_resolver import resolve_explore_list, build_bulk_search_jobs

    explore_destinations = [
        "Singapore", "Los Angeles", "New York", "Edinburgh",
        "Hong Kong", "Sydney", "Dublin", "Paris", "Toronto",
        "Lisbon", "Dubai", "Tokyo", "Berlin", "Malta",
    ]

    resolved = resolve_explore_list(
        explore_destinations,
        df_ranked=df,
        df_country_top=country_top,
        max_airports_per_dest=4,
        min_routes=5,
    )
    print("\nResolved destinations:")
    print(resolved[["input", "mode", "iso_country", "airports"]].head(10))

    jobs = build_bulk_search_jobs(
        origin_airports=["LHR", "LGW"],
        resolved_df=resolved,
        depart_date="2026-05-07",
        return_date=None,
        trip_type="one_way",
        max_destinations=10,
        max_airports_per_destination=2,
        max_origin_airports=2,
    )
    jobs_df = pd.DataFrame(jobs)
    jobs_path = os.path.join(BASE, "bulk_search_jobs.csv")
    jobs_df.to_csv(jobs_path, index=False)
    print(f"\nBuilt {len(jobs)} jobs. Saved: {jobs_path}")
    print("\nSample URL:")
    print(jobs[0]["url"])


if __name__ == "__main__":
    main()
