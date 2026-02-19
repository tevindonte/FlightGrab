"""
FlightGrab - Flight Deals Aggregator API
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from db_manager import FlightDatabase
from flight_scraper import TOP_50_US_AIRPORTS

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # cleanup if needed
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
@app.get("/healthz")
async def ping():
    """
    Lightweight keep-alive endpoint. No DB call.
    Use for: Render health checks, UptimeRobot / cron pings to keep the service active.
    """
    return {"status": "ok", "ping": "pong"}


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
                origins = TOP_50_US_AIRPORTS  # fallback
        else:
            origins = TOP_50_US_AIRPORTS
        return {"airports": origins}
    finally:
        db.close()


@app.get("/api/deals/all")
async def get_all_deals(
    period: str = Query("week", pattern="^(today|weekend|week|month)$"),
):
    """Get cheapest flights to each destination from ANY origin. Used for homepage global deals."""
    db = get_db()
    try:
        results = db.get_cheapest_from_all_origins(time_filter=period)
        return {"origin": "ALL", "period": period, "deals": results}
    finally:
        db.close()


@app.get("/api/deals")
async def get_deals(
    origin: str = Query(..., min_length=3, max_length=3),
    period: str = Query("today", pattern="^(today|weekend|week|month)$"),
):
    """Get cheapest flights from an origin (by departure date: today, weekend, week, month)."""
    origin = origin.upper()
    if origin not in TOP_50_US_AIRPORTS:
        raise HTTPException(status_code=400, detail=f"Unknown airport: {origin}")
    db = get_db()
    try:
        results = db.get_cheapest_from_origin(origin, time_filter=period)
        return {"origin": origin, "period": period, "deals": results}
    finally:
        db.close()


@app.get("/api/search")
async def search_route(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    period: str = Query("today", pattern="^(today|weekend|week|month)$"),
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
