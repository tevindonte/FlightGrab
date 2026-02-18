# Deploying FlightGrab on Render

## 1. Push code to GitHub

Ensure your FlightGrab project is in a Git repo and pushed to GitHub (or GitLab/Bitbucket).

```bash
git init
git add .
git commit -m "FlightGrab initial"
git remote add origin https://github.com/YOUR_USERNAME/CheapestFlights.git
git push -u origin main
```

## 2. Connect Render to the repo

1. Go to [dashboard.render.com](https://dashboard.render.com).
2. **New** → **Blueprint**.
3. Connect your Git provider and select the **CheapestFlights** repo.
4. Render will detect `render.yaml` and show the three services:
   - **flightgrab** (web)
   - **flightgrab-baseline** (cron)
   - **flightgrab-incremental** (cron)

## 3. Set DATABASE_URL

You must set `DATABASE_URL` for all three services (or use an [Environment Group](https://render.com/docs/configure-environment-variables#environment-groups) to share it).

- In the Blueprint, `DATABASE_URL` is set to `sync: false`, so Render will prompt you to enter it.
- When creating the Blueprint, add your **Neon PostgreSQL** connection string for each service that asks for it, e.g.:
  ```
  postgresql://user:password@host/dbname?sslmode=require
  ```

**Optional – Environment Group (recommended):**

1. In Render: **Environment Groups** → **New Environment Group** (e.g. `flightgrab-env`).
2. Add variable: `DATABASE_URL` = your Neon connection string.
3. In each service (flightgrab, flightgrab-baseline, flightgrab-incremental), add **Environment Group** → `flightgrab-env`.

Then you can remove the per-service `envVars` for `DATABASE_URL` from `render.yaml` and use:

```yaml
- fromGroup: flightgrab-env
```

instead (or set the group in the Dashboard for each service).

## 4. Deploy

- Click **Apply** (or let Render create the services). The **flightgrab** web service will build and deploy; your site will be at `https://flightgrab.onrender.com` (or the name you gave it).
- The two cron jobs will build; they won’t run until their schedule (or manual trigger).

## 5. Run baseline once (recommended: locally)

Render’s free tier has **512 MB RAM**. The baseline scraper (browser + parsing) often exceeds that, so **run baseline on your machine**, then use Render only for the web app and the **incremental** cron.

### Option A: Run baseline locally (recommended)

On your laptop (or any machine with enough RAM):

```bash
cd /path/to/FlightGrab
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require"   # or use .env
FULL_BASELINE=1 python daily_scraper.py baseline
```

- **FULL_BASELINE=1** = full **31 days**, **5 workers**. For 5 origins: ~1–1.5 hours. For 50 origins: change `NUM_ORIGINS = 50` in `daily_scraper.py`, then ~8–9 hours.
- After it finishes, the DB has the full 30-day window. No need to run baseline on Render.

Then on Render:

- **Delete** the **flightgrab-baseline** cron job (or leave it and never trigger it).
- Keep only **flightgrab-incremental** (runs daily at 3 AM UTC).

### Option B: Run baseline on Render (may OOM on free tier)

If you still have a baseline cron on Render:

1. Open **flightgrab-baseline** → **Trigger Run**.
2. Without `FULL_BASELINE`, it runs the **low-memory** path (7 days, sequential, ~45 min for 5 origins). It may still hit 512 MB; if it does, use Option A.

## 6. Daily incremental (automatic)

**flightgrab-incremental** runs at **3:00 AM UTC** every day (`0 3 * * *`). To change the time:

- Edit `render.yaml`: set `schedule` to a [cron expression](https://render.com/docs/cronjobs#schedule) (all times are UTC).
- Redeploy or re-sync the Blueprint.

Examples:

- `0 3 * * *` – 3 AM UTC daily (default)
- `0 8 * * *` – 8 AM UTC daily
- `0 */6 * * *` – every 6 hours

## 7. Scaling the scraper (NUM_ORIGINS)

In `daily_scraper.py`:

- `NUM_ORIGINS = 5` → baseline ~1 hr, incremental ~3.5 min (good for testing).
- `NUM_ORIGINS = 50` → baseline ~9 hr, incremental ~34 min (full production).

Push the change and re-deploy. For a one-off full baseline, trigger **flightgrab-baseline** again after increasing `NUM_ORIGINS` (or run baseline locally and only use Render for incremental).

## Summary

| Item | Action |
|------|--------|
| Web app | Deploys from Blueprint; live at your Render URL. |
| DATABASE_URL | Set in Dashboard (or via Environment Group) for flightgrab, flightgrab-baseline, flightgrab-incremental. |
| Baseline | Run **once**: Dashboard → flightgrab-baseline → **Trigger Run**. |
| Incremental | Runs automatically daily at 3 AM UTC (or your chosen schedule). |

## Troubleshooting

- **Cron job fails**: Check **Logs** for that cron service. Ensure `DATABASE_URL` is set and Neon allows connections from Render IPs (Neon usually allows all by default).
- **Web service 503**: Check **Logs**; often `DATABASE_URL` missing or wrong.
- **Baseline timeout**: Render cron jobs stop after 12 hours. With 5 origins, baseline fits; for 50-origin baseline (~9 hr), ensure the run finishes within 12 hours or run baseline locally and use Render only for the web app and incremental cron.
