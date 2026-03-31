"""
FlightGrab - Flight Deals Aggregator API
"""

import os
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Header, Body, Request
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from db_manager import FlightDatabase
from airport_names import get_city_name, parse_route_slug, route_slug

load_dotenv()

BASE_URL = os.getenv("APP_URL", "https://flightgrab.cc").rstrip("/")
ZEPTOMAIL_API_KEY = os.getenv("ZEPTOMAIL_API_KEY") or os.getenv("ZOHO_SMTP_PASSWORD")
ZEPTOMAIL_FROM = os.getenv("ZEPTOMAIL_FROM_EMAIL") or os.getenv("ZOHO_FROM_EMAIL", "noreply@flightgrab.cc")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
JWT_ALGORITHM = "HS256"


def _verify_auth_token(authorization: str | None) -> str | None:
    """Verify JWT and return user_id or None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        import jwt
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("user_id")
    except Exception:
        return None

# Lazy load Playwright-based generator (heavy dependency)
_booking_generator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db = FlightDatabase()
        db.connect()
        db.create_tables()
        db.close()
    except Exception:
        pass
    # Pre-warm sitemap cache so Google's first fetch gets instant response (avoids cold-start timeout)
    try:
        import time
        _sitemap_cache["xml"] = _build_sitemap_xml()
        _sitemap_cache["expires"] = time.time() + 3600
    except Exception:
        pass
    yield
    try:
        from booking_link_generator import close_generator
        await close_generator()
    except Exception:
        pass


app = FastAPI(
    title="FlightGrab API",
    description="Cheapest flight deals from major US airports",
    lifespan=lifespan,
)

# Serve static frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def get_db():
    db = FlightDatabase()
    try:
        db.connect()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")
    return db


@app.get("/ping")
@app.head("/ping")
@app.get("/healthz")
@app.head("/healthz")
async def ping():
    """
    Lightweight keep-alive endpoint. No DB call.
    Use for: Render health checks, UptimeRobot / cron pings to keep the service active.
    Supports both GET and HEAD (monitors often use HEAD).
    """
    return {"status": "ok", "ping": "pong"}


@app.get("/api/config")
async def get_config():
    """Public config for frontend."""
    return {"authMode": "custom"}


def _generate_verification_token():
    import secrets
    return secrets.token_urlsafe(32)


def _send_verification_email(email: str, token: str):
    """Send verification email via ZeptoMail. Does not raise if email fails."""
    if not ZEPTOMAIL_API_KEY:
        return
    try:
        from zeptomail import Config, Email
        verify_url = f"{BASE_URL}/verify?token={token}"
        config = Config(api_key=ZEPTOMAIL_API_KEY)
        mail = Email(config)
        mail.send(
            from_=ZEPTOMAIL_FROM,
            from_name="FlightGrab",
            to=[email],
            subject="Verify your FlightGrab account",
            html_body=f"""
                <h2>Welcome to FlightGrab!</h2>
                <p>Click the link below to verify your email:</p>
                <p><a href="{verify_url}">Verify Email</a></p>
                <p>Or copy this link: {verify_url}</p>
                <p>This link expires in 24 hours.</p>
            """,
        )
    except Exception as e:
        print(f"[FlightGrab] Failed to send verification email: {e}")


@app.post("/api/auth/signup")
async def auth_signup(body: dict = Body(...)):
    """Create account. Returns user + token."""
    import bcrypt
    import jwt
    import uuid

    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    first_name = (body.get("first_name") or "").strip()[:100]

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = "user_" + str(uuid.uuid4()).replace("-", "")[:24]
    verification_token = _generate_verification_token()

    db = get_db()
    try:
        ok = db.create_user(user_id, email, pw_hash, first_name, verification_token=verification_token)
        if not ok:
            raise HTTPException(status_code=400, detail="Email already registered")

        try:
            _send_verification_email(email, verification_token)
        except Exception:
            pass

        payload = {"user_id": user_id, "email": email, "exp": datetime.utcnow() + timedelta(days=30)}
        jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        if hasattr(jwt_token, "decode"):
            jwt_token = jwt_token.decode("utf-8")
        return {
            "user": {"id": user_id, "email": email, "first_name": first_name, "verified": False},
            "token": jwt_token,
        }
    finally:
        db.close()


@app.post("/api/auth/signin")
async def auth_signin(body: dict = Body(...)):
    """Sign in. Returns user + token."""
    import bcrypt
    import jwt

    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    db = get_db()
    try:
        u = db.get_user_by_email(email)
        if not u:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not bcrypt.checkpw(password.encode("utf-8"), u["password_hash"].encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        payload = {"user_id": u["id"], "email": u["email"], "exp": datetime.utcnow() + timedelta(days=30)}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        if hasattr(token, "decode"):
            token = token.decode("utf-8")
        verified = u.get("verified", True)
        return {
            "user": {
                "id": u["id"],
                "email": u["email"],
                "first_name": u["first_name"],
                "verified": verified,
            },
            "token": token,
        }
    finally:
        db.close()


@app.get("/api/auth/me")
async def auth_me(authorization: str = Header(None)):
    """Get current user. Requires valid token."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        u = db.get_user_by_id(user_id)
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": u["id"],
            "email": u["email"],
            "first_name": u["first_name"],
            "verified": u.get("verified", True),
        }
    finally:
        db.close()


@app.get("/verify")
async def verify_email(token: str = Query(..., description="Verification token from email")):
    """Verify email from link. Redirects to homepage with ?verified=true on success."""
    db = get_db()
    try:
        u = db.get_user_by_verification_token(token)
        if not u:
            return RedirectResponse(url=f"/?verified=invalid")
        db.verify_user(u["id"])
        return RedirectResponse(url=f"/?verified=true")
    finally:
        db.close()


@app.get("/robots.txt")
async def robots():
    """Allow all crawlers (required for AdSense verification)."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        "User-agent: *\nAllow: /\n\nSitemap: " + BASE_URL + "/sitemap.xml\n"
    )


@app.get("/ads.txt")
async def ads_txt():
    """AdSense ads.txt (required for AdSense monetization)."""
    from fastapi.responses import PlainTextResponse
    # Format: ad-system-domain, publisher-id, relationship, certification-authority-id
    return PlainTextResponse(
        "google.com, pub-2790122390767697, DIRECT, f08c47fec0942fa0\n"
    )


@app.get("/")
async def root():
    """Serve the FlightGrab homepage."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"app": "FlightGrab", "docs": "/docs"}


@app.get("/pricing")
async def pricing_page():
    """Serve the Pricing / Premium subscription page."""
    pricing_path = os.path.join(static_dir, "pricing.html")
    if os.path.isfile(pricing_path):
        return FileResponse(pricing_path)
    raise HTTPException(status_code=404, detail="Pricing page not found")


@app.get("/deals")
async def deals_page():
    """Serve the Explore All Deals page."""
    deals_path = os.path.join(static_dir, "deals.html")
    if os.path.isfile(deals_path):
        return FileResponse(deals_path)
    raise HTTPException(status_code=404, detail="Deals page not found")


@app.get("/flights/{route_slug}")
async def route_landing_page(request: Request, route_slug: str):
    """
    Route-specific landing page. URL format: /flights/ATL-to-MIA
    SEO-optimized page with flight options, stats, and travel guide.
    """
    origin_code, dest_code = parse_route_slug(route_slug)
    if not origin_code or not dest_code:
        raise HTTPException(status_code=404, detail="Route not found")

    db = get_db()
    try:
        flights = db.get_route_flights(origin_code, dest_code, limit=100)
        if not flights:
            raise HTTPException(status_code=404, detail="No flights found for this route")

        prices = [f["price"] for f in flights]
        cheapest_price = int(min(prices))
        avg_price = round(sum(prices) / len(prices), 0)
        savings = max(0, int(avg_price - cheapest_price))
        total_flights = len(flights)

        origin_name = get_city_name(origin_code)
        dest_name = get_city_name(dest_code)

        related = db.get_related_routes(origin_code, dest_code, limit=6)

        return templates.TemplateResponse(
            "route_page.html",
            {
                "request": request,
                "origin_code": origin_code,
                "dest_code": dest_code,
                "origin_name": origin_name,
                "dest_name": dest_name,
                "flights": flights,
                "cheapest_price": cheapest_price,
                "avg_price": int(avg_price),
                "total_flights": total_flights,
                "savings": savings,
                "related_routes": related,
            },
        )
    finally:
        db.close()


# In-memory cache for sitemap (avoids DB + cold-start timeout when Google retries)
_sitemap_cache: dict = {"xml": None, "expires": 0.0}
_SITEMAP_TTL = 3600  # 1 hour


def _build_sitemap_xml() -> str:
    """Generate sitemap XML. Called on cache miss."""
    db = get_db()
    try:
        routes = db.get_all_routes()
    finally:
        db.close()

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"  <url><loc>{BASE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"  <url><loc>{BASE_URL}/deals</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
    ]
    for page in ["about", "privacy", "terms"]:
        xml_lines.append(
            f"  <url><loc>{BASE_URL}/static/{page}.html</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>"
        )

    for r in routes:
        slug = route_slug(r["origin"], r["destination"])
        if slug:
            xml_lines.append(
                f"  <url><loc>{BASE_URL}/flights/{slug}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>"
            )

    xml_lines.append("</urlset>")
    return "\n".join(xml_lines)


@app.get("/sitemap.xml")
async def sitemap_xml():
    """
    XML sitemap for Google indexing. Cached for 1 hour to avoid cold-start timeouts.
    """
    import time
    now = time.time()
    if _sitemap_cache["xml"] and _sitemap_cache["expires"] > now:
        xml = _sitemap_cache["xml"]
    else:
        xml = _build_sitemap_xml()
        _sitemap_cache["xml"] = xml
        _sitemap_cache["expires"] = now + _SITEMAP_TTL

    return Response(
        content=xml,
        media_type="application/xml; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Robots-Tag": "all",
        },
    )


@app.get("/api/airports")
async def list_airports():
    """List airport codes (top 50 US). Optionally only those with data."""
    with_data = Query(False, description="If true, only return origins that have current data")
    db = get_db()
    try:
        if with_data:
            origins = db.get_origins_with_data()
            if not origins:
                from flight_scraper import TOP_50_US_AIRPORTS
                origins = TOP_50_US_AIRPORTS
        else:
            from flight_scraper import TOP_50_US_AIRPORTS
            origins = TOP_50_US_AIRPORTS
        return {"airports": origins}
    finally:
        db.close()


@app.get("/api/deals/all")
async def get_all_deals(
    period: str = Query("week", pattern="^(today|tomorrow|weekend|week|month|flexible|date|range)$"),
    client_date: str = Query(None, description="User's local date YYYY-MM-DD for today/tomorrow"),
    specific_date: str = Query(None, description="YYYY-MM-DD for single-date filter (use with period=date)"),
    date_from: str = Query(None, description="YYYY-MM-DD range start (use with period=range)"),
    date_to: str = Query(None, description="YYYY-MM-DD range end (use with period=range)"),
):
    """Get cheapest flights to each destination from ANY origin. Used for homepage global deals."""
    db = get_db()
    try:
        results = db.get_cheapest_from_all_origins(
            time_filter=period if period not in ("date", "range") else "week",
            client_date=client_date,
            specific_date=specific_date if period == "date" else None,
            date_from=date_from if period == "range" else None,
            date_to=date_to if period == "range" else None,
        )
        return {"origin": "ALL", "period": period, "deals": results}
    finally:
        db.close()


@app.get("/api/calendar/destinations")
async def get_calendar_destinations(
    origin: str = Query(..., min_length=3, max_length=3),
    limit: int = Query(200, ge=10, le=500),
):
    """Get all destinations from an origin with minimum price. For calendar destination search."""
    origin = origin.upper()
    db = get_db()
    try:
        destinations = db.get_calendar_destinations(origin, limit=limit)
        return {"origin": origin, "destinations": destinations}
    finally:
        db.close()


@app.get("/api/price-calendar")
async def get_price_calendar(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    days: int = Query(30, ge=7, le=60),
    date_from: str = Query(None, description="YYYY-MM-DD range start (overrides days)"),
    date_to: str = Query(None, description="YYYY-MM-DD range end"),
):
    """Get cheapest price per date for a route across the next N days or a date range."""
    origin, destination = origin.upper(), destination.upper()
    db = get_db()
    try:
        dates = db.get_price_calendar(origin, destination, days=days, date_from=date_from, date_to=date_to)
        return {"origin": origin, "destination": destination, "days": days, "dates": dates}
    finally:
        db.close()


@app.get("/api/return-flights")
async def get_return_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    outbound_date: str = Query(..., description="Outbound departure date YYYY-MM-DD"),
    min_days: int = Query(2, ge=1, le=90),
    max_days: int = Query(30, ge=1, le=90),
):
    """
    Get available return flights (reverse direction) for round-trip planning.
    E.g. outbound ATL→MIA, return MIA→ATL.
    """
    origin, destination = origin.upper(), destination.upper()
    db = get_db()
    try:
        flights = db.get_return_flights(origin, destination, outbound_date, min_days, max_days)
        return {
            "origin": origin,
            "destination": destination,
            "outbound_date": outbound_date,
            "flights": flights,
            "count": len(flights),
        }
    finally:
        db.close()


@app.get("/api/all-deals")
async def get_all_deals(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=100),
    origin: str = Query(None, min_length=3, max_length=3),
    destination: str = Query(None, min_length=3, max_length=3),
    max_price: float = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    date: str = Query(None, description="Single date YYYY-MM-DD"),
    stops: int = Query(None, ge=0, le=3, description="Exact stops (0=nonstop, 1=1 stop)"),
    airline: list = Query(None, description="Filter by airline (can repeat for multiple)"),
    time_of_day: str = Query(None, pattern="^(morning|afternoon|evening|night)$"),
    sort_by: str = Query("price", pattern="^(price|departure_date|origin|destination)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
):
    """
    Get all flights with filters and pagination. Powers /deals page.
    Returns flights + facets (available filter options).
    """
    db = get_db()
    try:
        airlines_list = [a.strip() for a in (airline or []) if a and str(a).strip()] or None
        flights, total = db.get_all_flights_paginated(
            page=page,
            limit=limit,
            origin=origin.upper() if origin else None,
            destination=destination.upper() if destination else None,
            max_price=max_price,
            date_from=date_from,
            date_to=date_to,
            date_exact=date,
            stops=stops,
            airlines=airlines_list,
            time_of_day=time_of_day,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        facets = db.get_all_deals_facets(
            origin=origin.upper() if origin else None,
            destination=destination.upper() if destination else None,
            max_price=max_price,
            date_from=date_from,
            date_to=date_to,
            date_exact=date,
            stops=stops,
            airlines=airlines_list,
            time_of_day=time_of_day,
        )
        return {
            "flights": flights,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit if total > 0 else 1,
            "facets": facets,
        }
    finally:
        db.close()


@app.get("/api/cheap-destinations")
async def cheap_destinations(
    max_price: int = Query(100, ge=1, le=1000),
    limit: int = Query(20, ge=5, le=50),
):
    """Get destinations with min price <= max_price. For 'fly under $X' widget."""
    db = get_db()
    try:
        results = db.get_cheap_destinations(max_price=float(max_price), limit=limit)
        enriched = [
            {**r, "destination_name": get_city_name(r["destination"])}
            for r in results
        ]
        return {"destinations": enriched}
    finally:
        db.close()


@app.get("/api/price-drops")
async def price_drops(
    limit: int = Query(6, ge=3, le=20),
):
    """Get routes with significant price drops (current min vs route average)."""
    db = get_db()
    try:
        results = db.get_price_drops(limit=limit)
        enriched = [
            {
                **r,
                "origin_name": get_city_name(r["origin"]),
                "destination_name": get_city_name(r["destination"]),
                "previous_price": r["avg_price"],
            }
            for r in results
        ]
        return {"drops": enriched}
    finally:
        db.close()


@app.get("/api/popular-routes")
async def popular_routes(
    limit: int = Query(10, ge=5, le=25),
):
    """Get routes with most flight options (proxy for popularity)."""
    db = get_db()
    try:
        results = db.get_popular_routes(limit=limit)
        enriched = [
            {
                **r,
                "origin_name": get_city_name(r["origin"]),
                "destination_name": get_city_name(r["destination"]),
            }
            for r in results
        ]
        return {"routes": enriched}
    finally:
        db.close()


@app.get("/api/deals")
async def get_deals(
    origin: str = Query(..., min_length=3, max_length=3),
    period: str = Query("week", pattern="^(today|tomorrow|weekend|week|month|flexible|date|range)$"),
    client_date: str = Query(None, description="User's local date YYYY-MM-DD for today/tomorrow"),
    specific_date: str = Query(None, description="YYYY-MM-DD for single-date filter (use with period=date)"),
    date_from: str = Query(None, description="YYYY-MM-DD range start (use with period=range)"),
    date_to: str = Query(None, description="YYYY-MM-DD range end (use with period=range)"),
):
    """Get cheapest flights from an origin."""
    origin = origin.upper()
    db = get_db()
    try:
        results = db.get_cheapest_from_origin(
            origin,
            time_filter=period if period not in ("date", "range") else "week",
            client_date=client_date,
            specific_date=specific_date if period == "date" else None,
            date_from=date_from if period == "range" else None,
            date_to=date_to if period == "range" else None,
        )
        return {"origin": origin, "period": period, "deals": results}
    finally:
        db.close()


@app.get("/api/search")
async def search_route(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    period: str = Query("today", pattern="^(today|tomorrow|weekend|week|month|flexible)$"),
):
    """Get best price for a specific route (by departure window)."""
    origin, destination = origin.upper(), destination.upper()
    db = get_db()
    try:
        result = db.search_route(origin, destination, time_filter=period)
        if result is None:
            raise HTTPException(status_code=404, detail="No data for this route")
        return result
    finally:
        db.close()


@app.get("/api/route-flights")
async def api_route_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    departure_date: Optional[str] = Query(None, description="Optional filter YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=200),
):
    """
    Public JSON list of stored flights for a route (for FlightGrab Python package and integrations).
    """
    from fastapi.encoders import jsonable_encoder

    origin, destination = origin.upper(), destination.upper()
    db = None
    try:
        db = get_db()
        flights = db.get_route_flights(
            origin, destination, limit=limit, departure_date=departure_date or None
        )
        return jsonable_encoder({"origin": origin, "destination": destination, "flights": flights})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"route-flights: {str(e)}")
    finally:
        if db is not None:
            db.close()


@app.get("/api/book-redirect")
async def book_redirect(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str = Query(..., description="Departure date YYYY-MM-DD"),
    format: str = Query(None, description="If 'json', return URL in JSON instead of redirect"),
):
    """
    Generate fresh OTA booking link by simulating Continue click on Google Flights.
    User clicks card -> this endpoint -> Playwright clicks -> redirect to airline.
    Falls back to Google Flights booking page if generation fails.
    """
    origin = origin.upper()
    destination = destination.upper()

    db = get_db()
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            """
            SELECT google_booking_url, booking_url
            FROM current_prices
            WHERE origin = %s AND destination = %s AND departure_date = %s
            ORDER BY price ASC
            LIMIT 1
            """,
            (origin, destination, date),
        )
        row = cursor.fetchone()
        cursor.close()
        google_booking_url = row[0] if row and row[0] else None
        booking_url = row[1] if row and len(row) > 1 and row[1] else None
    finally:
        db.close()

    final_url = None

    # Pre-extracted airline URL (from batch refresh): instant redirect, no Cloud Run needed
    if booking_url and "google.com" not in (booking_url or "").lower():
        final_url = booking_url
    else:
        fallback = (
            "https://www.google.com/travel/flights?q="
            + urllib.parse.quote(f"One way flights from {origin} to {destination} on {date}")
        )

        # For extract-from-search, use tfs (protobuf) URL - it works; simple ?q= often fails "Did not reach booking page"
        search_url = fallback
        if not google_booking_url:
            try:
                import sys
                from pathlib import Path
                rev_path = Path(__file__).parent / "reverse_engineering_scraping"
                if str(rev_path) not in sys.path:
                    sys.path.insert(0, str(rev_path.parent))
                from reverse_engineering_scraping.tfs_encoder import build_flights_url_from_iata
                search_url = build_flights_url_from_iata(
                    slices_iata=[(date, origin, destination)],
                    adults=1, cabin="economy", trip_type="one_way", sort="cheapest",
                )
            except Exception:
                pass

        cloud_run_url = (os.getenv("CLOUD_RUN_URL") or os.getenv("LINK_EXTRACTOR_URL") or "").strip().rstrip("/")

        # Cloud Run: /extract for booking URL (fast), /extract-from-search when we only have search URL (slower but gets airline).
        if cloud_run_url:
            endpoint = "/extract-from-search" if not google_booking_url else "/extract"
            url_param = search_url if not google_booking_url else google_booking_url
            try:
                import httpx
                async with httpx.AsyncClient(timeout=55.0) as client:
                    resp = await client.get(f"{cloud_run_url}{endpoint}", params={"url": url_param})
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("success") and data.get("url"):
                            final_url = data["url"]
            except Exception:
                pass

        if not final_url and google_booking_url:
            try:
                from booking_link_generator import get_generator

                generator = await get_generator()
                fresh_link = await generator.get_fresh_booking_link(google_booking_url, timeout_ms=25000)
                if fresh_link:
                    final_url = fresh_link
            except ImportError:
                pass
            except Exception:
                pass

            if not final_url:
                final_url = google_booking_url

        if not final_url:
            final_url = fallback

    if format == "json":
        return JSONResponse(content={"url": final_url})
    return RedirectResponse(url=final_url)


@app.get("/api/subscription/status")
async def get_subscription_status(authorization: str = Header(None)):
    """Get user's subscription status and alert limits."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        status = db.get_subscription_status(user_id)
        return status
    finally:
        db.close()


@app.post("/api/alerts/subscribe")
async def subscribe_alert(
    body: dict = Body(...),
    authorization: str = Header(None),
):
    """Subscribe to price alert. Requires Clerk auth. Free users limited to 5 alerts."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    user_id_body = body.get("user_id")
    if user_id_body and user_id_body != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    origin = (body.get("origin") or "")[:3].upper()
    destination = (body.get("destination") or "")[:3].upper()
    target_price = float(body.get("target_price", 0))
    email = (body.get("email") or "").strip()
    if not origin or len(origin) != 3 or not destination or len(destination) != 3 or target_price <= 0:
        raise HTTPException(status_code=400, detail="Invalid origin, destination, or target price")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    db = get_db()
    try:
        alert_id = db.subscribe_alert(user_id, email, origin, destination, target_price)
        return {"id": alert_id, "status": "active"}
    except ValueError as e:
        if str(e) == "ALERT_LIMIT_REACHED":
            raise HTTPException(
                status_code=402,
                detail="Upgrade to Premium for unlimited alerts",
            )
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@app.get("/api/alerts")
async def get_my_alerts(authorization: str = Header(None)):
    """Get user's active alerts. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        alerts = db.get_user_alerts(user_id)
        return {"alerts": alerts}
    finally:
        db.close()


@app.delete("/api/alerts/{alert_id:int}")
async def delete_alert(alert_id: int, authorization: str = Header(None)):
    """Deactivate an alert. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        ok = db.deactivate_alert(alert_id, user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"status": "deleted"}
    finally:
        db.close()


@app.post("/api/subscription/checkout")
async def create_checkout_session(authorization: str = Header(None)):
    """Create Stripe Checkout session for Premium. Redirects user to Stripe-hosted payment page."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        u = db.get_user_by_id(user_id)
        if u and not u.get("verified", True):
            raise HTTPException(
                status_code=400,
                detail="Please verify your email before upgrading to Premium",
            )
    finally:
        db.close()
    stripe_secret = os.getenv("STRIPE_SECRET_KEY")
    stripe_price_id = os.getenv("STRIPE_PRICE_ID")
    if not stripe_secret or not stripe_price_id:
        raise HTTPException(status_code=503, detail="Premium checkout not configured")
    try:
        import stripe
        stripe.api_key = stripe_secret
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": stripe_price_id, "quantity": 1}],
            success_url=f"{BASE_URL}/pricing?success=true",
            cancel_url=f"{BASE_URL}/pricing?canceled=true",
            customer_email=None,
            metadata={"user_id": user_id},
            subscription_data={"metadata": {"user_id": user_id}},
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks for subscription lifecycle."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        return Response(status_code=200)
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")
    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        user_id = sess.get("metadata", {}).get("user_id") or sess.get("subscription_data", {}).get("metadata", {}).get("user_id")
        sub_id = sess.get("subscription")
        if user_id and sub_id:
            db = get_db()
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                period_end = datetime.fromtimestamp(sub["current_period_end"]) if sub.get("current_period_end") else None
                db.upsert_subscription(user_id, status="active", stripe_subscription_id=sub_id, current_period_end=period_end)
            finally:
                db.close()
    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        user_id = sub.get("metadata", {}).get("user_id")
        if user_id:
            db = get_db()
            try:
                status = "active" if sub.get("status") in ("active", "trialing") else "canceled"
                period_end = datetime.fromtimestamp(sub["current_period_end"]) if sub.get("current_period_end") else None
                db.upsert_subscription(user_id, status=status, stripe_subscription_id=sub["id"], current_period_end=period_end)
            finally:
                db.close()
    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        user_id = sub.get("metadata", {}).get("user_id")
        if user_id:
            db = get_db()
            try:
                db.upsert_subscription(user_id, status="free", stripe_subscription_id=None, current_period_end=None)
            finally:
                db.close()
    return Response(status_code=200)


@app.post("/api/saved-flights")
async def save_flight(
    body: dict = Body(...),
    authorization: str = Header(None),
):
    """Save a route. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    origin = (body.get("origin") or "")[:3].upper()
    destination = (body.get("destination") or "")[:3].upper()
    notes = (body.get("notes") or "").strip() or None
    if not origin or len(origin) != 3 or not destination or len(destination) != 3:
        raise HTTPException(status_code=400, detail="Invalid origin or destination")
    db = get_db()
    try:
        saved_id = db.save_flight(user_id, origin, destination, notes)
        return {"id": saved_id, "status": "saved"}
    finally:
        db.close()


@app.get("/api/saved-flights")
async def get_saved_flights(authorization: str = Header(None)):
    """Get user's saved flights. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        flights = db.get_user_saved_flights(user_id)
        return {"saved_flights": flights}
    finally:
        db.close()


@app.get("/api/date-preferences")
async def get_date_preferences(authorization: str = Header(None)):
    """Get user's saved date range. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        return {"date_from": None, "date_to": None}
    db = get_db()
    try:
        prefs = db.get_user_date_preferences(user_id)
        return prefs or {"date_from": None, "date_to": None}
    finally:
        db.close()


@app.post("/api/date-preferences")
async def save_date_preferences(
    body: dict = Body(...),
    authorization: str = Header(None),
):
    """Save preferred date range. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    date_from = (body.get("date_from") or "").strip()[:10]
    date_to = (body.get("date_to") or "").strip()[:10]
    if not date_from or not date_to:
        raise HTTPException(status_code=400, detail="date_from and date_to required (YYYY-MM-DD)")
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
    db = get_db()
    try:
        ok = db.save_user_date_preferences(user_id, date_from, date_to)
        if not ok:
            raise HTTPException(status_code=400, detail="Invalid date format")
        return {"status": "saved", "date_from": date_from, "date_to": date_to}
    finally:
        db.close()


@app.delete("/api/saved-flights/{saved_id:int}")
async def delete_saved_flight(saved_id: int, authorization: str = Header(None)):
    """Delete a saved flight. Requires Clerk auth."""
    user_id = _verify_auth_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required")
    db = get_db()
    try:
        ok = db.delete_saved_flight(saved_id, user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Saved flight not found")
        return {"status": "deleted"}
    finally:
        db.close()


@app.get("/api/health")
async def health(strict: bool = Query(False, description="If true, return 503 when DB is unreachable")):
    """
    Reports database connectivity. By default returns HTTP 200 so load balancers / Render deploy
    probes that hit this URL do not fail the whole deploy on a transient DB error.

    Prefer configuring your host to probe GET /ping (no DB). Use ?strict=true for a probe that
    must fail (503) when Postgres is down.
    """
    try:
        db = FlightDatabase()
        db.connect()
        db.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        detail = str(e)
        if strict:
            raise HTTPException(status_code=503, detail=detail)
        return JSONResponse(
            status_code=200,
            content={
                "status": "degraded",
                "database": "disconnected",
                "detail": detail,
            },
        )
