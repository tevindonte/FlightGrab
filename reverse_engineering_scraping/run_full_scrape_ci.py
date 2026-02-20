"""
Run full scrape as GitHub Actions would (single worker).
Usage:
  WORKER_ID=1 TOTAL_WORKERS=4 python run_full_scrape_ci.py
  python run_full_scrape_ci.py --worker-id 1 --total-workers 4
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))

from dotenv import load_dotenv
load_dotenv()

from scrape_and_save_pipeline import run_pipeline

TOTAL_WORKERS = int(os.environ.get("TOTAL_WORKERS", "4"))
MAX_JOBS_PER_RUN = int(os.environ.get("MAX_JOBS_PER_RUN", "100"))
MAX_COUNTRIES = int(os.environ.get("MAX_COUNTRIES", "150"))


def main():
    worker_id = os.environ.get("WORKER_ID")
    if not worker_id:
        print("Set WORKER_ID=1..4 (or pass --worker-id)")
        sys.exit(1)
    try:
        wid = int(worker_id)
    except ValueError:
        print("WORKER_ID must be 1-4")
        sys.exit(1)
    run_pipeline(
        mode="popular",
        max_countries=MAX_COUNTRIES,
        max_jobs_per_run=MAX_JOBS_PER_RUN,
        worker_id=wid,
        total_workers=TOTAL_WORKERS,
        concurrency=2,
        headless=True,
        save_to_db=True,
    )


if __name__ == "__main__":
    main()
