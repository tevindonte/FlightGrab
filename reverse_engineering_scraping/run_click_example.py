"""
Run click scraper on bulk jobs and save results to CSV.
  python run_click_example.py
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import asyncio
import pandas as pd
from scraper_click import run_click_scraper

JOBS_PATH = os.path.join(BASE, "bulk_search_jobs.csv")
OUTPUT_PATH = os.path.join(BASE, "click_results.csv")


def main():
    if not os.path.exists(JOBS_PATH):
        print("Run run_example.py first to build bulk_search_jobs.csv")
        sys.exit(1)

    jobs = pd.read_csv(JOBS_PATH).head(2)  # quick test: 2 jobs
    profile = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "gflights_profile_click")

    print(f"Running scraper on {len(jobs)} jobs, max 2 clicks each...")
    df = asyncio.run(
        run_click_scraper(
            jobs,
            concurrency=1,
            headless=True,
            max_items_per_search=2,
            user_data_dir=profile,
            output_path=OUTPUT_PATH,
        )
    )
    print(f"Saved: {OUTPUT_PATH}")
    print(f"Rows: {len(df)}, OK: {df['ok'].sum()}")


if __name__ == "__main__":
    main()
