"""
FlightGrab - Flight Deals Aggregator API
"""

import os
import urllib.parse
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Body
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from db_manager import FlightDatabase

load_dotenv()


def _verify_clerk_token(authorization: str | None) -> str | None:
    """Verify Clerk JWT and return user_id (sub claim) or None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    jwks_url = os.getenv("CLERK_JWKS_URL")
    if not jwks_url:
        return None
    try:
        import jwt
        from jwt import PyJWKClient
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(token, signing_key.key, algorithms=["RS256"])
        return payload.get("sub")
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
    db.connect()
    try:
        return db
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


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
    """Public config for frontend (Clerk key, etc.)."""
    return {
        "clerkPublishableKey": os.getenv("CLERK_PUBLISHABLE_KEY", ""),
    }


@app.get("/robots.txt")
async def robots():
    """Allow all crawlers (required for AdSense verification)."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        "User-agent: *\nAllow: /\n"
    )


@app.get("/")
async def root():
    """Serve the FlightGrab homepage."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"app": "FlightGrab", "docs": "/docs"}


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


@app.get("/api/book-redirect")
async def book_redirect(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str = Query(..., description="Departure date YYYY-MM-DD"),
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

    # Pre-extracted airline URL (from batch refresh): instant redirect, no Cloud Run needed
    if booking_url and "google.com" not in (booking_url or "").lower():
        return RedirectResponse(url=booking_url)

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
                        return RedirectResponse(url=data["url"])
        except Exception:
            pass

    # Fallback: local Playwright (only works if we have booking URL; fails on Render)
    if google_booking_url:
        try:
            from booking_link_generator import get_generator

            generator = await get_generator()
            fresh_link = await generator.get_fresh_booking_link(google_booking_url, timeout_ms=25000)
            if fresh_link:
                return RedirectResponse(url=fresh_link)
        except ImportError:
            pass
        except Exception:
            pass

        return RedirectResponse(url=google_booking_url)

    return RedirectResponse(url=fallback)


@app.post("/api/alerts/subscribe")
async def subscribe_alert(
    body: dict = Body(...),
    authorization: str = Header(None),
):
    """Subscribe to price alert. Requires Clerk auth."""
    user_id = _verify_clerk_token(authorization)
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
    finally:
        db.close()


@app.get("/api/alerts")
async def get_my_alerts(authorization: str = Header(None)):
    """Get user's active alerts. Requires Clerk auth."""
    user_id = _verify_clerk_token(authorization)
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
    user_id = _verify_clerk_token(authorization)
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


@app.post("/api/saved-flights")
async def save_flight(
    body: dict = Body(...),
    authorization: str = Header(None),
):
    """Save a route. Requires Clerk auth."""
    user_id = _verify_clerk_token(authorization)
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
    user_id = _verify_clerk_token(authorization)
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
    user_id = _verify_clerk_token(authorization)
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
    user_id = _verify_clerk_token(authorization)
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
    user_id = _verify_clerk_token(authorization)
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
async def health():
    """Health check; verifies DB connectivity."""
    try:
        db = FlightDatabase()
        db.connect()
        db.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
