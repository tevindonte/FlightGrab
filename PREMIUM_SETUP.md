# Premium Subscription Setup

FlightGrab Premium ($9.99/month) gives users unlimited price alerts. Free users are limited to 5 alerts.

## What's Implemented

- **Database**: `user_subscriptions` table (created automatically on app start)
- **Alert limit**: Free users can create up to 5 alerts; Premium users have unlimited
- **API**: 
  - `GET /api/subscription/status` — returns `is_premium`, `alert_count`, `alert_limit`, `can_add_more`
  - `POST /api/subscription/checkout` — creates Stripe Checkout session, returns redirect URL
  - `POST /api/webhooks/stripe` — handles subscription lifecycle (activate, renew, cancel)
- **UI**: 
  - `/pricing` page with Free vs Premium comparison
  - Alert modal shows "X of 5 alerts" and upgrade CTA when at limit
  - My Alerts modal shows upgrade CTA when at limit
  - 402 response on subscribe triggers "Upgrade to Premium" redirect

## Stripe Setup

### 1. Create Stripe account and products

1. Go to [Stripe Dashboard](https://dashboard.stripe.com)
2. **Products** → Add product: "FlightGrab Premium"
3. Add a recurring price: **$9.99/month**
4. Copy the **Price ID** (e.g. `price_1ABC123...`)

### 2. Environment variables

Add to your `.env` (or Render/hosting env):

```
STRIPE_SECRET_KEY=sk_live_xxx          # or sk_test_xxx for testing
STRIPE_PRICE_ID=price_xxx              # The $9.99/month price ID
STRIPE_WEBHOOK_SECRET=whsec_xxx       # From Stripe webhook setup (below)
```

### 3. Webhook configuration

1. **Developers** → **Webhooks** → Add endpoint
2. Endpoint URL: `https://your-domain.com/api/webhooks/stripe`
3. Select events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy the **Signing secret** (starts with `whsec_`) → `STRIPE_WEBHOOK_SECRET`

### 4. Local webhook testing

Use [Stripe CLI](https://stripe.com/docs/stripe-cli) to forward webhooks:

```bash
stripe listen --forward-to localhost:8000/api/webhooks/stripe
```

Use the CLI's printed `whsec_...` as `STRIPE_WEBHOOK_SECRET` for local dev.

## Testing

1. **Without Stripe**: App runs normally. Checkout returns 503; users see "Premium checkout not available yet."
2. **With Stripe (test mode)**:
   - Use `sk_test_...` and test price ID
   - Create an alert, hit 5 alerts, try 6th → see upgrade prompt
   - Sign in, go to /pricing, click "Upgrade to Premium" → Stripe Checkout
   - Use test card `4242 4242 4242 4242`
   - After payment, webhook should set `user_subscriptions.status = 'active'`
   - User can now add unlimited alerts

## Auth (Clerk) – Optional

- **CLERK_ACCOUNTS_URL** – Base URL for Clerk hosted sign-in (default: `https://accounts.flightgrab.cc`). Override if your Clerk instance uses a different domain.

## Revenue expectation

- 100 Premium users × $9.99 ≈ **$1,000/month**
- Target: 50–100 subscribers in first 3 months via in-app upsells and SEO
