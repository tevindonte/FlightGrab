"""Test: Verify priority routes appear first in job builder."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "reverse_engineering_scraping"))

from full_job_builder import build_full_jobs

# Use max_countries=20 for fast test with US origins (full run ~1 min)
jobs = build_full_jobs(max_countries=20)
df = jobs
print("First 5 jobs:")
for i, row in enumerate(df.head(5).to_dict("records")):
    print(f"  {i+1}. {row['origin']} -> {row['dest']}")
print(f"Total jobs: {len(df)}")
