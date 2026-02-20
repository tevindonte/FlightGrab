# Full Location Scraper – GitHub Actions

## Overview

The **Full Location Scraper** runs daily at 4 AM UTC via `.github/workflows/scrape-full-locations.yml`. It scrapes flight data from Google Flights for:

- **Origins**: Top airports from ~150 countries (`country_top_airports.csv`)
- **Destinations**: Popular explore-style cities (Singapore, Dubai, Paris, etc.)
- **Paired routes**: For each A→B, also scrapes B→A

## Worker Distribution

| Workers | Jobs per run | Total jobs/day | Coverage |
|---------|--------------|----------------|----------|
| 4       | ~100 each    | ~400           | Rotates daily |

Jobs are **sharded by index**: Worker 1 gets jobs 0,4,8,... Worker 2 gets 1,5,9,... etc. Each worker runs independently and writes to the same DB (UPSERT handles conflicts).

## Environment Variables (Workflow)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (secret) | Neon PostgreSQL connection string |
| `WORKER_ID` | 1–4 | Which worker is running |
| `TOTAL_WORKERS` | 4 | Total parallel workers |
| `MAX_JOBS_PER_RUN` | 100 | Cap jobs per worker (fits ~35 min timeout) |
| `MAX_COUNTRIES` | 150 | Limit countries for job building |

## Time Estimates

- ~20–30 sec per job (navigate, click, capture booking URL)
- 80 jobs × 25 sec ≈ **33 min** (fits 35 min timeout)
- 4 workers × 80 jobs ≈ **320 routes/day**

## Local Testing (Simulate CI)

```bash
cd reverse_engineering_scraping

# Simulate worker 1
WORKER_ID=1 TOTAL_WORKERS=4 MAX_JOBS_PER_RUN=20 python run_full_scrape_ci.py

# Or use pipeline directly
python scrape_and_save_pipeline.py --mode popular --max-countries 20 \
  --max-jobs-per-run 50 --worker-id 1 --total-workers 4
```

## Scaling

- **More workers**: Add jobs `scrape-full-5`, `scrape-full-6`, etc. and set `TOTAL_WORKERS=6`
- **Faster coverage**: Increase `MAX_JOBS_PER_RUN` (risk timeout) or run workflow multiple times per day
- **Full coverage**: Set `MAX_COUNTRIES` to `null`/empty for all ~200 countries (job build will be slower due to Wikidata lookups)

## Dependencies

Requires `playwright` and Chromium. The workflow runs:

```bash
pip install -r requirements.txt
pip install -r reverse_engineering_scraping/requirements.txt
playwright install chromium
```
