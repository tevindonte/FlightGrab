# Price Alerts & User Accounts Setup

## 1. Clerk (Authentication)

1. Create account at [clerk.com](https://clerk.com)
2. Create an application, get your keys
3. Add to `.env`:
   ```
   CLERK_PUBLISHABLE_KEY=pk_test_xxxx
   CLERK_JWKS_URL=https://<your-clerk-domain>/.well-known/jwks.json
   ```
   - Find JWKS URL in Clerk Dashboard → JWT Templates, or use your Frontend API + `/.well-known/jwks.json`

## 2. Zoho ZeptoMail (Email)

1. Create account at [zoho.com/zeptomail](https://www.zoho.com/zeptomail/) or use ZeptoMail from Zoho
2. Verify your domain (e.g. flightgrab.cc)
3. Get SMTP credentials from ZeptoMail dashboard (Server: smtp.zeptomail.com)
4. Add to `.env`:
   ```
   ZOHO_SMTP_PASSWORD=<your ZeptoMail API key / password>
   ZOHO_FROM_EMAIL=noreply@flightgrab.cc
   ```
   Optional overrides: `ZOHO_SMTP_SERVER`, `ZOHO_SMTP_PORT` (587 or 465), `ZOHO_SMTP_USER` (default: emailapikey)
5. Add GitHub secret:
   - `ZOHO_SMTP_PASSWORD` (in repo → Settings → Secrets)

## 3. Run Migrations

```bash
python db_manager.py
```

This creates the `price_alerts` and `saved_flights` tables.

## 4. Test Alert Checker Locally

```bash
python alert_checker.py
```

## 5. GitHub Actions

The workflow at `.github/workflows/check-alerts.yml` runs daily at 4:30 AM UTC.

- **Secrets** (Settings → Secrets and variables → Actions):
  - `DATABASE_URL`
  - `ZOHO_SMTP_PASSWORD`
- **Variables** (Settings → Secrets and variables → Actions):
  - `ZOHO_FROM_EMAIL` (e.g. noreply@flightgrab.cc)
  - `APP_URL` (e.g. https://flightgrab.cc) – used for "Manage alerts" link in emails
