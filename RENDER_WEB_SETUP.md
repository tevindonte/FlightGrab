# Render Web Service – FlightGrab (step-by-step)

Use these values when creating the **Web Service** in the Render dashboard.

---

## Keep the service awake (free tier)

The app has a **lightweight ping endpoint** you can hit so the service stays active:

- **URL**: `https://YOUR-SERVICE.onrender.com/ping` or `/healthz`
- **Use with**: [UptimeRobot](https://uptimerobot.com), [cron-job.org](https://cron-job.org), or any monitor that pings every 5–10 minutes.

Set your monitor to GET `https://flightgrab.onrender.com/ping` (replace with your real URL) every 5–10 min so the free instance doesn’t spin down.

---

## Option A: Docker (if Build Command doesn’t show)

If the form only shows Docker options (Dockerfile path, etc.):

1. **Language**: leave as **Docker**.
2. **Dockerfile Path**: `./Dockerfile` (or leave default).
3. **Docker Command**: leave empty (the Dockerfile already runs uvicorn).
4. **Environment Variables**: add `DATABASE_URL` = your Neon connection string.
5. **Health Check Path**: `/ping` or `/healthz` (lightweight, no DB).

No build or start commands needed; the repo’s `Dockerfile` handles build and run.

---

## Option B: Python (if you see Build Command)

If you can choose **Python** as the runtime:

1. **Language**: **Python**.
2. **Build Command**: `pip install -r requirements.txt`
3. **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables**: add `DATABASE_URL` = your Neon connection string.
5. **Health Check Path**: `/ping` or `/healthz`

---

## Common settings (either option)

| Field               | Value |
|---------------------|--------|
| **Name**            | FlightGrab |
| **Branch**          | main |
| **Region**          | Ohio or Oregon |
| **Root Directory**  | *(empty)* |
| **Env var**         | `DATABASE_URL` = Neon URL |
| **Health Check Path** | `/ping` or `/healthz` |

- **/ping** and **/healthz** – fast, no database (best for health checks and keep-alive pings).
- **/api/health** – checks DB as well; use if you want the health check to verify the database.

---

## After deploy

1. Open `https://YOUR-SERVICE.onrender.com/ping` – should return `{"status":"ok","ping":"pong"}`.
2. Add a free uptime monitor (e.g. UptimeRobot) to ping `/ping` every 5–10 minutes so the free instance stays awake.
