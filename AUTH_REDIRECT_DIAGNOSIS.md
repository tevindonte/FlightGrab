# FlightGrab Auth Redirect Issue – Diagnosis Report

**Issue:** When users click "Sign In" or "Sign Up," they are redirected to `https://accounts.flightgrab.cc/sign-up?redirect_url=...`, then the page reloads and returns them to the homepage. The auth modal does not open.

**Date:** February 2025

---

## 1. Summary

The FlightGrab codebase uses **custom email/password auth** with in-page modals. It does **not** use Clerk for authentication. However, Clerk is still configured in the environment and is associated with the domain `flightgrab.cc`. Clerk automatically provisions `accounts.flightgrab.cc` for its Account Portal. The redirect to `accounts.flightgrab.cc` is almost certainly triggered **outside** the FlightGrab application code—by Clerk’s infrastructure, DNS, a proxy/CDN, or external links.

---

## 2. Current Auth Setup (FlightGrab)

### 2.1 What the app does

| Component | Implementation |
|-----------|----------------|
| **Auth method** | Custom JWT (email + password, bcrypt) |
| **Sign In / Sign Up UI** | In-page modal (no navigation) |
| **Homepage** | Buttons `#btn-sign-in`, `#btn-sign-up` → `openAuthModal()` in `app.js` |
| **Deals page** | Links `#link-signin`, `#link-signup` → `auth.js` opens modal in-place |
| **Pricing page** | Same as Deals |
| **API** | `POST /api/auth/signin`, `POST /api/auth/signup` |

### 2.2 What the app does NOT do

- Does **not** load any Clerk script (`@clerk/clerk-js`, `clerk.js`, etc.)
- Does **not** link to `accounts.flightgrab.cc`
- Does **not** redirect to `/sign-in` or `/sign-up`
- Uses `/#signin` and `/#signup` only for in-page handling

---

## 3. Clerk Configuration and `accounts.flightgrab.cc`

### 3.1 Environment variables

```env
CLERK_PUBLISHABLE_KEY=pk_live_Y2xlcmsuZmxpZ2h0Z3JhYi5jYyQ
CLERK_SECRET_KEY=sk_live_...
CLERK_JWKS_URL=https://busy-turkey-91.clerk.accounts.dev/.well-known/jwks.json
```

The base64-decoded publishable key includes `clerk.flightgrab.cc`, so this Clerk instance is tied to `flightgrab.cc`.

### 3.2 Clerk’s default behavior

From [Clerk Account Portal docs](https://clerk.com/docs/guides/account-portal/getting-started), when a production domain is configured, Clerk automatically creates:

- `https://accounts.<your-domain>.com/sign-in`
- `https://accounts.<your-domain>.com/sign-up`
- `https://accounts.<your-domain>.com/user`
- etc.

So `accounts.flightgrab.cc` is Clerk’s default Account Portal for this domain.

### 3.3 What Clerk needs to redirect users

Clerk can send users to `accounts.flightgrab.cc` if:

1. **Clerk SDK/Components are loaded** – e.g. `<SignIn>`, `<SignUp>`, or `@clerk/clerk-js`.  
   **Status:** Not found in the FlightGrab HTML or JS.

2. **Direct links** – Any link to `https://accounts.flightgrab.cc/sign-in` or `/sign-up`.  
   **Status:** Not found in the codebase.

3. **Clerk Dashboard config** – If the Clerk Dashboard has `flightgrab.cc` as a production domain, `accounts.flightgrab.cc` is active regardless of whether the app uses Clerk.

4. **External sources** – Emails, ads, bookmarks, or other sites linking to `accounts.flightgrab.cc`.

---

## 4. Possible Causes of the Redirect

### 4.1 DNS / Clerk infrastructure

- `accounts.flightgrab.cc` may be a CNAME to Clerk’s servers (e.g. `*.accounts.dev`).
- Clerk provisions this automatically when the domain is configured.
- Visiting `accounts.flightgrab.cc` shows Clerk’s hosted auth UI; Clerk can then redirect back via `redirect_url`.

### 4.2 Proxy / CDN rules

- If the app sits behind Cloudflare, Render proxy, or another CDN, there may be rules like:
  - Redirect `/sign-in` → `https://accounts.flightgrab.cc/sign-in`
  - Redirect `/sign-up` → `https://accounts.flightgrab.cc/sign-up`
- FlightGrab does not define routes for `/sign-in` or `/sign-up`, so such rules would only apply if configured at the proxy layer.

### 4.3 Clerk SDK loaded elsewhere

- A different frontend (e.g. Next.js, React app) that uses Clerk and loads the publishable key could drive users to the Account Portal.
- The production site might be serving a different build or branch than the repo being analyzed.

### 4.4 Link interception or rewriting

- Browser extensions, “smart” links, or ad scripts could rewrite links.
- AdSense code is present; ads could theoretically contain links to Clerk or other auth flows (unusual but possible).

### 4.5 User flow confusion

- User might:
  - Click a link from an email or external site going to `accounts.flightgrab.cc`
  - Land on `accounts.flightgrab.cc`, then Clerk redirects to `redirect_url=https://flightgrab.cc/`
  - End up on the homepage without the intended auth modal or hash

---

## 5. What Happens End-to-End

1. User intends to sign in or sign up.
2. Something causes navigation to `https://accounts.flightgrab.cc/sign-up?redirect_url=https://flightgrab.cc/`.
3. Clerk’s Account Portal loads.
4. Then the page “reloads” and sends the user back to `https://flightgrab.cc/`.
5. The in-page modal does not open because:
   - The URL is `https://flightgrab.cc/` (no `#signin` or `#signup`), and/or
   - The redirect originates from Clerk, not from the FlightGrab app.

---

## 6. Repo Verification Summary

| Check | Result |
|-------|--------|
| Clerk script in HTML | None found |
| Links to `accounts.flightgrab.cc` | None found |
| `/sign-in` or `/sign-up` routes in `app.py` | None |
| Homepage Sign In/Sign Up | Buttons → `openAuthModal()` (no link) |
| Deals/Pricing Sign In/Sign Up | `auth.js` opens modal in-place, `href="#"` |
| `render.yaml` or other infra redirects | None found |
| Clerk env vars | Present |

---

## 7. Recommended Next Steps (for second opinion)

1. **Inspect live production markup**
   - View page source of `https://flightgrab.cc` and `https://flightgrab.cc/deals`.
   - Search for:
     - `clerk`
     - `accounts.flightgrab`
     - `accounts.dev`
     - Any script loading Clerk SDK or components.

2. **Check DNS**
   - Run `dig accounts.flightgrab.cc` or `nslookup accounts.flightgrab.cc`.
   - See if it points to Clerk’s infrastructure.

3. **Check proxy/CDN configuration**
   - If using Cloudflare, Render, Vercel, etc., review redirect and rewrite rules for:
     - `/sign-in`, `/sign-up`, or other auth paths
     - Any rules involving `accounts.flightgrab.cc` or Clerk URLs.

4. **Review Clerk Dashboard**
   - Confirm if `flightgrab.cc` is configured as a production domain.
   - Check what happens when users visit `accounts.flightgrab.cc` directly.
   - Optionally disable or remove the `accounts.flightgrab.cc` setup if Clerk is no longer used.

5. **Test without external factors**
   - Use incognito/private mode.
   - Disable extensions.
   - Confirm which exact element (button, link, ad) triggers the redirect.

---

## 8. Conclusion

The FlightGrab application code uses custom auth and does not integrate with Clerk. The redirect to `accounts.flightgrab.cc` is consistent with Clerk’s Account Portal being active for `flightgrab.cc`, but the trigger appears to be outside the application—likely Clerk’s setup, DNS, proxy rules, or external links. A second opinion should focus on:

1. Confirming there is no Clerk usage in the deployed HTML/JS.
2. Identifying how the user actually reaches `accounts.flightgrab.cc`.
3. Deciding whether to fully remove Clerk’s configuration and `accounts.flightgrab.cc` if Clerk is no longer in use.
