# GitHub Actions Setup Guide

## What This Does

Runs 4 parallel scrapers daily on GitHub's infrastructure (7 GB RAM each):

| Worker | Origins (airports) | Count |
|--------|--------------------|-------|
| 1 | ATL, DFW, DEN, ORD, LAX, CLT, MCO, LAS, PHX, MIA, SEA, IAH, EWR | 13 |
| 2 | SFO, BOS, MSP, DTW, FLL, JFK, LGA, PHL, BWI, DCA, IAD, SAN, SLC | 13 |
| 3 | TPA, PDX, HNL, AUS, MDW, BNA, DAL, RDU, STL, HOU, SJC, MCI | 12 |
| 4 | OAK, SAT, RSW, IND, CMH, CVG, PIT, SMF, CLE, MKE, SNA, ANC | 12 |

**Runtime:** ~15–20 min (all 4 run in parallel)  
**Cost:** Free (within GitHub Actions limits)

---

## Setup

### 1. Add `DATABASE_URL` Secret

1. Repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Name: `DATABASE_URL`
4. Value: Your Neon connection string, e.g.  
   `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`

### 2. Push to GitHub

```bash
git add .github/workflows/scrape-flights.yml daily_scraper.py
git commit -m "Add GitHub Actions distributed scraping"
git push origin main
```

### 3. Test Run

1. **Actions** tab → **Daily Flight Scraper**
2. **Run workflow** → **Run workflow**
3. Wait ~15 min for all 4 workers

---

## Schedule

- **Automatic:** 3:00 AM UTC daily
- **Manual:** Actions → Daily Flight Scraper → Run workflow
  - Options: run all workers, or worker 1, 2, 3, or 4 only

---

## Local Test

```powershell
$env:WORKER_ID = "1"
python daily_scraper.py incremental
```

---

## Keep on Render

- Web app (FastAPI)
- Serves frontend and API

Scraping moves to GitHub Actions; web app still reads from Neon.
