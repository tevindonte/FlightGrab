"""
Destination resolver: city/country/IATA -> candidate airports (IATA list).
Uses airport_ranked.csv and country_top_airports.csv from airport_ranking.py.
"""

import ast
import re
from typing import Optional

import pandas as pd

try:
    from tfs_encoder import build_flights_url_from_iata
except ImportError:
    from .tfs_encoder import build_flights_url_from_iata  # when run as package

COUNTRY_NAME_TO_ISO2 = {
    "united states": "US", "usa": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "ireland": "IE", "canada": "CA",
    "france": "FR", "spain": "ES", "italy": "IT", "germany": "DE",
    "netherlands": "NL", "portugal": "PT", "greece": "GR", "turkey": "TR",
    "uae": "AE", "united arab emirates": "AE",
    "china": "CN", "hong kong": "HK", "japan": "JP", "south korea": "KR", "india": "IN",
    "singapore": "SG",
    "australia": "AU", "new zealand": "NZ",
    "iceland": "IS", "norway": "NO", "malta": "MT",
}

CITY_ALIASES = {
    "washington, d.c.": ("washington", "US"),
    "washington dc": ("washington", "US"),
    "washington d c": ("washington", "US"),
    "d.c.": ("washington", "US"),
    "d c": ("washington", "US"),
    "berlin": ("schonefeld", "DE"),
    "berlin germany": ("schonefeld", "DE"),
}

LABEL_FIXES = {
    "washington dc": "washington, d.c.",
    "washington d c": "washington, d.c.",
}


def _strip_accents_basic(s: str) -> str:
    return (
        s.replace("ö", "o").replace("ä", "a").replace("ü", "u")
        .replace("ß", "ss")
        .replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("á", "a").replace("à", "a").replace("â", "a")
        .replace("í", "i").replace("ì", "i").replace("î", "i")
        .replace("ó", "o").replace("ò", "o").replace("ô", "o")
        .replace("ú", "u").replace("ù", "u").replace("û", "u")
    )


def norm(s: str) -> str:
    s = str(s).strip().lower()
    s = _strip_accents_basic(s)
    s = re.sub(r"[\.\,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_iata(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{3}", str(s).strip().upper()))


def resolve_country_iso2(text: str) -> Optional[str]:
    t = norm(text)
    if t in COUNTRY_NAME_TO_ISO2:
        return COUNTRY_NAME_TO_ISO2[t]
    if re.fullmatch(r"[A-Za-z]{2}", str(text).strip()):
        return str(text).strip().upper()
    return None


def _real_airports_only(sub: pd.DataFrame) -> pd.DataFrame:
    if sub.empty:
        return sub
    return sub[sub["type"].isin(["large_airport", "medium_airport", "small_airport"])].copy()


def _safe_upper_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().str.strip()


def _prep_rank_frames(
    df_ranked: pd.DataFrame, df_country_top: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_ranked = df_ranked.copy()
    df_country_top = df_country_top.copy()
    for c in ["iata_code", "iso_country", "type", "municipality", "name"]:
        if c in df_ranked.columns:
            df_ranked[c] = df_ranked[c].astype("string")
    for c in ["iata_code", "iso_country", "type"]:
        if c in df_country_top.columns:
            df_country_top[c] = df_country_top[c].astype("string")
    if "route_count" not in df_ranked.columns:
        df_ranked["route_count"] = 0
    if "major_score" not in df_ranked.columns:
        df_ranked["major_score"] = 0.0
    df_ranked["route_count"] = pd.to_numeric(df_ranked["route_count"], errors="coerce").fillna(0).astype(int)
    df_ranked["major_score"] = pd.to_numeric(df_ranked["major_score"], errors="coerce").fillna(0.0)
    if "route_count" not in df_country_top.columns:
        df_country_top["route_count"] = 0
    if "major_score" not in df_country_top.columns:
        df_country_top["major_score"] = 0.0
    df_country_top["route_count"] = pd.to_numeric(df_country_top["route_count"], errors="coerce").fillna(0).astype(int)
    df_country_top["major_score"] = pd.to_numeric(df_country_top["major_score"], errors="coerce").fillna(0.0)
    return df_ranked, df_country_top


def _filter_and_pick_airports(sub: pd.DataFrame, max_airports: int) -> tuple[list[str], Optional[str]]:
    if sub.empty:
        return [], None
    sub = sub.sort_values(["major_score", "route_count"], ascending=False)
    iso_guess = str(sub.iloc[0].get("iso_country", "")).strip() or None
    if iso_guess:
        sub = sub[_safe_upper_series(sub["iso_country"]) == iso_guess.upper()]
    airports = _safe_upper_series(sub["iata_code"]).head(max_airports).tolist()
    return airports, iso_guess


def candidate_airports_for_destination(
    dest: str,
    df_ranked: pd.DataFrame,
    df_country_top: pd.DataFrame,
    max_airports: int = 6,
    min_routes: int = 5,
) -> dict:
    raw = str(dest).strip()
    if not raw:
        return {"input": dest, "mode": "empty", "iso_country": None, "airports": []}

    raw_norm = norm(raw)
    if raw_norm in LABEL_FIXES:
        raw = LABEL_FIXES[raw_norm]
        raw_norm = norm(raw)

    if is_iata(raw):
        code = raw.upper()
        hit = df_ranked[_safe_upper_series(df_ranked["iata_code"]) == code]
        if not hit.empty:
            iso = str(hit.iloc[0].get("iso_country", "")).strip() or None
            return {"input": dest, "mode": "iata_direct", "iso_country": iso, "airports": [code]}
        return {"input": dest, "mode": "iata_unknown", "iso_country": None, "airports": [code]}

    t = raw_norm

    iso2 = resolve_country_iso2(raw)
    if iso2:
        sub = df_country_top[_safe_upper_series(df_country_top["iso_country"]) == iso2.upper()].copy()
        sub = _real_airports_only(sub)
        airports, _ = _filter_and_pick_airports(sub, max_airports=max_airports)
        return {"input": dest, "mode": "country", "iso_country": iso2, "airports": airports}

    iso_hint = None
    if t in CITY_ALIASES:
        t, iso_hint = CITY_ALIASES[t]

    muni = df_ranked["municipality"].astype(str).str.lower().fillna("").apply(_strip_accents_basic)
    sub_city = df_ranked[muni.str.contains(re.escape(t), na=False)].copy()
    sub_city = _real_airports_only(sub_city)
    sub_city = sub_city[sub_city["route_count"] >= int(min_routes)].copy()
    if iso_hint:
        sub_city = sub_city[_safe_upper_series(sub_city["iso_country"]) == iso_hint.upper()].copy()
    if not sub_city.empty:
        airports, iso_guess = _filter_and_pick_airports(sub_city, max_airports=max_airports)
        return {"input": dest, "mode": "city_match", "iso_country": iso_guess, "airports": airports}

    nm = df_ranked["name"].astype(str).str.lower().fillna("").apply(_strip_accents_basic)
    sub_name = df_ranked[nm.str.contains(re.escape(t), na=False)].copy()
    sub_name = _real_airports_only(sub_name)
    sub_name = sub_name[sub_name["route_count"] >= int(min_routes)].copy()
    if iso_hint:
        sub_name = sub_name[_safe_upper_series(sub_name["iso_country"]) == iso_hint.upper()].copy()
    if not sub_name.empty:
        airports, iso_guess = _filter_and_pick_airports(sub_name, max_airports=max_airports)
        return {"input": dest, "mode": "airport_name_match", "iso_country": iso_guess, "airports": airports}

    return {"input": dest, "mode": "unresolved", "iso_country": None, "airports": []}


def resolve_explore_list(
    destinations: list[str],
    df_ranked: pd.DataFrame,
    df_country_top: pd.DataFrame,
    max_airports_per_dest: int = 6,
    min_routes: int = 5,
) -> pd.DataFrame:
    df_ranked, df_country_top = _prep_rank_frames(df_ranked, df_country_top)
    rows = []
    for d in destinations:
        rows.append(
            candidate_airports_for_destination(
                d,
                df_ranked=df_ranked,
                df_country_top=df_country_top,
                max_airports=max_airports_per_dest,
                min_routes=min_routes,
            )
        )
    return pd.DataFrame(rows)


def _coerce_airports_cell(x) -> list:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return list(x)
    try:
        import numpy as np
        if isinstance(x, np.ndarray):
            return x.tolist()
    except Exception:
        pass
    try:
        if pd.isna(x):
            return []
    except Exception:
        pass
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                v = ast.literal_eval(s)
                if isinstance(v, (list, tuple, set)):
                    return list(v)
            except Exception:
                pass
        return re.findall(r"[A-Z0-9]{3}", s.upper())
    return []


def build_bulk_search_jobs(
    origin_airports: list[str],
    resolved_df: pd.DataFrame,
    depart_date: str,
    return_date: Optional[str] = None,
    trip_type: str = "one_way",
    cabin: str = "economy",
    adults: int = 1,
    max_destinations: int = 40,
    max_airports_per_destination: int = 2,
    max_origin_airports: int = 2,
    sort: str = "best",
) -> list[dict]:
    import itertools

    origin_airports = [x.upper() for x in origin_airports if is_iata(x)]
    origin_airports = origin_airports[:max_origin_airports]
    jobs = []
    df_use = resolved_df.copy().head(max_destinations)

    for _, row in df_use.iterrows():
        dest_label = row.get("input", None)
        mode = row.get("mode", None)
        iso_country = row.get("iso_country", None)
        dest_airports_raw = _coerce_airports_cell(row.get("airports", None))
        dest_airports = [x.upper() for x in dest_airports_raw if is_iata(x)]
        dest_airports = dest_airports[:max_airports_per_destination]
        if not dest_airports:
            continue

        for o, d in itertools.product(origin_airports, dest_airports):
            if trip_type == "one_way":
                slices_iata = [(depart_date, o, d)]
            else:
                if not return_date:
                    raise ValueError("round_trip requires return_date")
                slices_iata = [(depart_date, o, d), (return_date, d, o)]

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
                "dest_label": dest_label,
                "mode": mode,
                "iso_country": iso_country,
                "trip_type": trip_type,
                "depart_date": depart_date,
                "return_date": return_date if trip_type != "one_way" else None,
                "cabin": cabin,
                "adults": adults,
                "sort": sort,
                "url": url,
            })
    return jobs
