# GitHub Actions – Secrets & Variables

For scrape summary emails to work, configure these in your GitHub repo.

## Required

1. Go to **Repository → Settings → Secrets and variables → Actions**

### Secrets (encrypted)

| Secret | Used by | Description |
|--------|---------|-------------|
| `DATABASE_URL` | All scrapers | Neon PostgreSQL connection string |
| `ZOHO_SMTP_PASSWORD` | Scrape summary, Price alerts | Zoho ZeptoMail API key (same as price alerts) |

### Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `ZOHO_FROM_EMAIL` | `noreply@flightgrab.cc` | Sender address for emails |
| `SCRAPE_SUMMARY_EMAIL` | `tparboosingh84@gmail.com` | Where to send scrape summary |

## Getting ZOHO_SMTP_PASSWORD

1. Sign up at [zoho.com/zeptomail](https://www.zoho.com/zeptomail/)
2. In ZeptoMail dashboard: **SMTP & API** → create/copy API key
3. Add as secret `ZOHO_SMTP_PASSWORD` in GitHub

(Same credentials used for price alert emails in the app.)

## Workflows that send email

- **Daily Flight Scraper** (3 AM UTC) – sends summary after scraping US flight prices
- **Full Location Scraper** (4 AM UTC) – sends summary after scraping international routes

If `ZOHO_SMTP_PASSWORD` is missing, the workflow will fail at the summary step. The summary stats are always printed to the workflow log, so you can still see the numbers in the Actions tab.
