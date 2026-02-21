"""
Build full scrape jobs: all country airports × popular/all destinations, with paired routes.
For each origin→dest we also include dest→origin (roundtrip-effect pairing).
"""

from __future__ import annotations

import os
from typing import List, Optional

import pandas as pd

try:
    from .destination_resolver import (
        build_bulk_search_jobs,
        resolve_explore_list,
        candidate_airports_for_destination,
        is_iata,
    )
    from .tfs_encoder import build_flights_url_from_iata
except ImportError:
    from destination_resolver import (
        build_bulk_search_jobs,
        resolve_explore_list,
        candidate_airports_for_destination,
        is_iata,
    )
    from tfs_encoder import build_flights_url_from_iata

# Default popular destinations (Flights Explore–style)
DEFAULT_EXPLORE_DESTINATIONS = [
    "Singapore", "Los Angeles", "New York", "Edinburgh", "Hong Kong",
    "Sydney", "Dublin", "Paris", "Toronto", "Lisbon", "Dubai", "Tokyo",
    "Berlin", "Malta", "Barcelona", "Amsterdam", "Rome", "Madrid",
    "Istanbul", "Thailand", "Portugal", "Greece",
    "London", "Mexico City", "Costa Rica", "Miami", "San Francisco",
    "Las Vegas", "Cancun", "Punta Cana", "Bahamas", "Jamaica",
]

# High-value routes to prioritize (scraped first when in job set)
PRIORITY_ROUTES = [
    ("JFK", "LHR"), ("LAX", "NRT"), ("SFO", "HKG"), ("MIA", "LHR"),
    ("JFK", "CDG"), ("LAX", "LHR"), ("ORD", "LHR"), ("SFO", "NRT"),
    ("ATL", "LHR"), ("DFW", "LHR"), ("JFK", "FCO"), ("LAX", "SYD"),
]


def load_country_airports(
    path: Optional[str] = None,
    top_per_country: int = 5,
    min_routes: int = 5,
) -> pd.DataFrame:
    """Load country_top_airports and return top N airports per country."""
    if path is None:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "country_top_airports.csv")
    df = pd.read_csv(path)
    df = df[df["route_count"].fillna(0) >= min_routes].copy()
    df["iso_country"] = df["iso_country"].astype(str).str.upper().str.strip()
    # Top N per country by major_score
    out = (
        df.sort_values(["iso_country", "major_score", "route_count"], ascending=[True, False, False])
        .groupby("iso_country", as_index=False)
        .head(top_per_country)
    )
    return out


def get_origin_airports(country_top: pd.DataFrame, max_per_country: int = 5) -> List[str]:
    """Unique origin airports across all countries."""
    codes = country_top["iata_code"].astype(str).str.upper().str.strip().dropna()
    codes = codes[codes.str.match(r"[A-Z0-9]{3}", na=False)]
    return codes.unique().tolist()


def get_all_dest_airports(country_top: pd.DataFrame, exclude_iso: Optional[List[str]] = None) -> List[str]:
    """All destination airports (same as origins, optionally excluding countries)."""
    df = country_top.copy()
    if exclude_iso:
        df = df[~df["iso_country"].isin([c.upper() for c in exclude_iso])]
    codes = df["iata_code"].astype(str).str.upper().str.strip().dropna()
    codes = codes[codes.str.match(r"[A-Z0-9]{3}", na=False)]
    return codes.unique().tolist()


def build_paired_jobs(
    origin_airports: List[str],
    dest_airports: List[str],
    depart_date: str,
    trip_type: str = "one_way",
    cabin: str = "economy",
    adults: int = 1,
    sort: str = "best",
    ensure_both_directions: bool = True,
) -> List[dict]:
    """
    Build jobs for origin×dest with pairing: for each (o,d) we include both o→d and d→o
    when both o and d are in our airport sets.
    """
    jobs = []
    seen = set()

    for o in origin_airports:
        for d in dest_airports:
            if o == d:
                continue
            if (o, d) in seen:
                continue
            seen.add((o, d))
            slices_iata = [(depart_date, o, d)]
            try:
                url = build_flights_url_from_iata(
                    slices_iata=slices_iata,
                    adults=adults,
                    cabin=cabin,
                    trip_type=trip_type,
                    sort=sort,
                    hl="en",
                    debug=False,
                )
                jobs.append({
                    "origin": o,
                    "dest": d,
                    "dest_label": d,
                    "mode": "iata",
                    "iso_country": None,
                    "trip_type": trip_type,
                    "depart_date": depart_date,
                    "return_date": None,
                    "cabin": cabin,
                    "adults": adults,
                    "sort": sort,
                    "url": url,
                })
            except Exception:
                continue

            if ensure_both_directions and (d, o) not in seen:
                seen.add((d, o))
                slices_rev = [(depart_date, d, o)]
                try:
                    url_rev = build_flights_url_from_iata(
                        slices_iata=slices_rev,
                        adults=adults,
                        cabin=cabin,
                        trip_type=trip_type,
                        sort=sort,
                        hl="en",
                        debug=False,
                    )
                    jobs.append({
                        "origin": d,
                        "dest": o,
                        "dest_label": o,
                        "mode": "iata",
                        "iso_country": None,
                        "trip_type": trip_type,
                        "depart_date": depart_date,
                        "return_date": None,
                        "cabin": cabin,
                        "adults": adults,
                        "sort": sort,
                        "url": url_rev,
                    })
                except Exception:
                    pass

    return jobs


def build_full_jobs(
    mode: str = "popular",
    depart_date: Optional[str] = None,
    top_origins_per_country: int = 3,
    max_countries: Optional[int] = None,
    max_popular_destinations: int = 40,
    explore_destinations: Optional[List[str]] = None,
    country_top_path: Optional[str] = None,
    ranked_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Build the full job set.

    Args:
        mode: "popular" = origins×explore destinations; "all" = origins×all other country airports
        depart_date: YYYY-MM-DD (default: ~3 months out)
        top_origins_per_country: max airports per country as origins
        max_countries: limit number of countries (for testing)
        max_popular_destinations: cap explore destinations
        explore_destinations: override default popular list
        country_top_path: path to country_top_airports.csv
        ranked_path: path to airport_ranked.csv (for resolve_explore_list)

    Returns:
        DataFrame with columns: origin, dest, dest_label, url, depart_date, ...
    """
    from datetime import datetime, timedelta

    if depart_date is None:
        depart_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

    base = os.path.dirname(os.path.abspath(__file__))
    country_top_path = country_top_path or os.path.join(base, "country_top_airports.csv")
    ranked_path = ranked_path or os.path.join(base, "airport_ranked.csv")

    country_top = load_country_airports(country_top_path, top_per_country=top_origins_per_country)

    if max_countries:
        countries = country_top["iso_country"].unique()[:max_countries]
        country_top = country_top[country_top["iso_country"].isin(countries)]

    origin_airports = get_origin_airports(country_top, max_per_country=top_origins_per_country)

    if mode == "popular":
        if not os.path.exists(ranked_path):
            from airport_ranking import load_and_score
            df_ranked = load_and_score()
        else:
            df_ranked = pd.read_csv(ranked_path)
        df_country = pd.read_csv(country_top_path) if os.path.exists(country_top_path) else country_top

        dest_list = explore_destinations or DEFAULT_EXPLORE_DESTINATIONS
        resolved = resolve_explore_list(
            dest_list[:max_popular_destinations],
            df_ranked=df_ranked,
            df_country_top=df_country,
            max_airports_per_dest=4,
            min_routes=5,
        )
        import ast
        dest_airports = []
        for _, row in resolved.iterrows():
            ap = row.get("airports")
            if ap is None:
                continue
            if isinstance(ap, str):
                ap = ast.literal_eval(ap) if (ap.strip().startswith("[") and ap.strip().endswith("]")) else [ap]
            if not isinstance(ap, (list, tuple)):
                ap = [ap]
            dest_airports.extend([str(x).upper() for x in ap if x and is_iata(str(x))])
        dest_airports = list(dict.fromkeys(dest_airports))

    else:
        dest_airports = get_all_dest_airports(country_top)

    jobs = build_paired_jobs(
        origin_airports=origin_airports,
        dest_airports=dest_airports,
        depart_date=depart_date,
        ensure_both_directions=True,
    )

    # Prepend priority routes (ensure high-value pairs get scraped first)
    origin_set = set(origin_airports)
    dest_set = set(dest_airports)
    seen = {(j["origin"], j["dest"]) for j in jobs}
    priority_jobs = []
    for o, d in PRIORITY_ROUTES:
        if o in origin_set and d in dest_set and (o, d) not in seen:
            try:
                url = build_flights_url_from_iata(
                    slices_iata=[(depart_date, o, d)],
                    trip_type="one_way",
                    cabin="economy",
                    adults=1,
                    sort="best",
                    hl="en",
                    debug=False,
                )
                priority_jobs.append({
                    "origin": o, "dest": d, "dest_label": d,
                    "mode": "iata", "iso_country": None, "trip_type": "one_way",
                    "depart_date": depart_date, "return_date": None,
                    "cabin": "economy", "adults": 1, "sort": "best", "url": url,
                })
                seen.add((o, d))
            except Exception:
                pass
    jobs = priority_jobs + jobs

    return pd.DataFrame(jobs)
