# Google Flights Reverse Engineering — Scraping Pipeline

This folder contains reverse-engineered code for building Google Flights URLs, resolving destinations to airports, and scraping flight results + booking links.

---

## One-Way Pipeline (6 Steps)

1. **Destination list** — human-style: "Singapore", "Canada", "Berlin", "Dubai"
2. **Destination Resolver** — maps each to ranked IATA airports (e.g. "Singapore" → SIN; "Canada" → YYZ, YVR, ...)
3. **Build search URLs** — for each (origin, dest, date), encode tfs (IATA→MID via Wikidata) → Google Flights URL
4. **Open search page** — Playwright navigates to URL; **[STUCK]** reliably detect flight result rows
5. **Click result** — click "Select flight" → opens booking page
6. **Extract links** — from booking page: airline links, partner links, external booking URLs

---

## Where We Left Off

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Destination → Airports | ✅ Done | `destination_resolver.py` — handles cities, countries, IATA, aliases (Washington D.C., Berlin) |
| 2. Airports → Search URLs | ✅ Done | `tfs_encoder.py` — protobuf-in-base64url, Wikidata IATA→MID |
| 3. Search page → Click results | ⚠️ Stuck | Selectors (`li[role="listitem"]`, `div[role="listitem"]`, "Select flight") not reliably matching real DOM |
| 4. Booking page → Links | ✅ Implemented | Extract external links from booking page |

**Current blocker:** Reliably detect the list of flight results on the Google Flights search page before we can click into booking pages.

---

## File Layout

| File | Purpose |
|------|---------|
| `tfs_encoder.py` | Protobuf tfs encode/decode, IATA→Freebase MID via Wikidata, `build_flights_url_from_iata` |
| `airport_ranking.py` | OurAirports + OpenFlights → `airport_ranked.csv`, `country_top_airports.csv` |
| `destination_resolver.py` | `candidate_airports_for_destination`, `resolve_explore_list`, country/city mapping |
| `bulk_job_builder.py` | `build_bulk_search_jobs` — origin × dest × dates → job list with URLs |
| `scraper_search.py` | Basic search scrape (price extraction, GBP forcing, consent handling) |
| `scraper_click.py` | Click "Select flight" → booking page → extract external links |
| `full_job_builder.py` | Build jobs: all country airports × popular/all destinations, paired (A→B and B→A) |
| `scrape_and_save_pipeline.py` | Full pipeline: jobs → scrape → save to DB |
| `consent_utils.py` | Cookie seeding, consent gate detection, consent button clicks |
| `requirements.txt` | Dependencies |

---

## Usage (High Level)

```python
# 1. Build airport data (run once)
# python airport_ranking.py

# 2. Resolve destinations → airports
from destination_resolver import resolve_explore_list
resolved = resolve_explore_list(destinations, df_ranked, country_top)

# 3. Build bulk search jobs
from bulk_job_builder import build_bulk_search_jobs
jobs = build_bulk_search_jobs(origin_airports=["LHR"], resolved_df=resolved, ...)

# 4. Scrape (when selectors work)
# await run_scraper(jobs_df)  or  await run_click_scraper(jobs_df)
```

---

## Quick Start

```bash
cd reverse_engineering_scraping
pip install -r requirements.txt
playwright install chromium

# 1. Build airport data + bulk jobs
python run_example.py

# 2. (Optional) Run search scraper (extracts prices)
# python -c "import asyncio; from scraper_search import main_async; asyncio.run(main_async(limit=3))"

# 3. Run click scraper (extracts booking links)
# python run_click_example.py

# 4. Full pipeline (all countries → popular destinations, paired routes, DB save)
# python scrape_and_save_pipeline.py --max-countries 5 --max-jobs 50
# python scrape_and_save_pipeline.py --help
```

---

## Notes

- **Flights SEARCH** uses Freebase MIDs (`/m/...`) in dep/arr. IATA → MID via Wikidata (P238, P646).
- **Flights EXPLORE (Anywhere)** uses a different tfs schema; best approach: scrape Explore page → extract "View flights" links → those are standard flights tfs.
- GBP: append `hl=en-GB&gl=GB&curr=GBP` to URLs.
- Consent: `CONSENT` + `SOCS` cookies can pre-seed; otherwise click "Accept all" in main page or iframe.
