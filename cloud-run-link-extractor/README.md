# Link Extractor – Google Cloud Run (FREE tier)

Standalone Playwright service that extracts airline/OTA URLs from Google Flights booking pages.

**Architecture:** Your main app stays on Render (free). Cloud Run (free) handles ONLY Playwright when users click "Book Now."

## Deploy

```powershell
cd C:\Users\tparb\Documents\CheapestFlights\cloud-run-link-extractor

gcloud run deploy link-extractor --source . --region us-central1 --platform managed --allow-unauthenticated --memory 2Gi --cpu 1 --timeout 60 --max-instances 10 --min-instances 0
```

**Note:** First deploy may take 5–10 min. If build fails, check [Cloud Build logs](https://console.cloud.google.com/cloud-build/builds).

## API

- **GET /health** – Health check
- **GET /extract?url=...** – Returns `{ success: true, url: "https://..." }` or `{ success: false, fallback_url: "..." }`

## Integrate with Render

1. After deploy, copy the Cloud Run URL (e.g. `https://link-extractor-xxx.a.run.app`)
2. In **Render dashboard** → your web service → **Environment** → Add:
   ```
   CLOUD_RUN_URL = https://link-extractor-xxx.a.run.app
   ```
3. Redeploy the main app on Render.

`app.py` will call Cloud Run first; if it fails, it falls back to local Playwright or the Google Flights URL.

## Free Tier

- **Cloud Run:** 2M requests/month, 360K GB-seconds free
- **Typical usage:** ~30K requests/month = well under free tier
- **Total cost:** $0/month
