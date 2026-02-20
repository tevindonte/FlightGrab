"""
Build airport_ranked.csv and country_top_airports.csv from OurAirports + OpenFlights routes.
- Scores airports by type + outbound/inbound connectivity
- build_country_airport_map ensures EVERY country has >= 1 airport
"""

import numpy as np
import pandas as pd

OURAIRPORTS_AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OPENFLIGHTS_ROUTES = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"

TYPE_SCORE = {
    "large_airport": 2.0,
    "medium_airport": 1.0,
    "small_airport": 0.25,
}

DEFAULT_MIN_ROUTES = 10
DEFAULT_TOPK_PER_COUNTRY = 15


def load_and_score() -> pd.DataFrame:
    air_raw = pd.read_csv(OURAIRPORTS_AIRPORTS_CSV)
    air = air_raw.copy()
    air["iata_code"] = air["iata_code"].where(air["iata_code"].notna(), None)
    air["iata_code"] = air["iata_code"].astype("string").str.upper().str.strip()
    air = air[air["iata_code"].notna()]
    air = air[air["iata_code"].str.fullmatch(r"[A-Z0-9]{3}", na=False)].copy()
    air["iso_country"] = air["iso_country"].astype("string").str.upper().str.strip()
    air["municipality"] = air["municipality"].astype("string")
    keep_cols = ["iata_code", "name", "type", "municipality", "iso_country", "latitude_deg", "longitude_deg"]
    for c in keep_cols:
        if c not in air.columns:
            air[c] = np.nan
    air = air[keep_cols].copy()

    routes = pd.read_csv(
        OPENFLIGHTS_ROUTES,
        header=None,
        names=[
            "airline", "airline_id", "source_airport", "source_airport_id",
            "dest_airport", "dest_airport_id", "codeshare", "stops", "equipment",
        ],
        dtype=str,
    )
    for c in ["source_airport", "dest_airport"]:
        routes[c] = routes[c].astype("string").str.upper().str.strip()
    routes = routes[
        routes["source_airport"].str.fullmatch(r"[A-Z0-9]{3}", na=False)
        & routes["dest_airport"].str.fullmatch(r"[A-Z0-9]{3}", na=False)
    ].copy()

    outgoing = (
        routes.groupby("source_airport")["dest_airport"]
        .nunique()
        .reset_index(name="route_count")
        .rename(columns={"source_airport": "iata_code"})
    )
    inbound = (
        routes.groupby("dest_airport")["source_airport"]
        .nunique()
        .reset_index(name="inbound_route_count")
        .rename(columns={"dest_airport": "iata_code"})
    )

    df = air.merge(outgoing, on="iata_code", how="left").merge(inbound, on="iata_code", how="left")
    df["route_count"] = df["route_count"].fillna(0).astype(int)
    df["inbound_route_count"] = df["inbound_route_count"].fillna(0).astype(int)
    df["type_score"] = df["type"].map(TYPE_SCORE).fillna(0.0)
    df["major_score"] = (
        df["type_score"]
        + np.log1p(df["route_count"]) / 2.5
        + np.log1p(df["inbound_route_count"]) / 3.5
    )
    df = df.sort_values(["iso_country", "major_score", "route_count"], ascending=[True, False, False]).reset_index(drop=True)
    return df


def top_airports_by_country(
    df_in: pd.DataFrame,
    iso_country: str,
    n: int = 15,
    min_routes: int = DEFAULT_MIN_ROUTES,
    allowed_types=("large_airport", "medium_airport", "small_airport"),
) -> pd.DataFrame:
    iso_country = str(iso_country).upper().strip()
    sub = df_in[df_in["iso_country"].astype("string").str.upper().str.strip() == iso_country].copy()
    sub = sub[sub["type"].isin(allowed_types)]
    sub = sub[sub["route_count"] >= int(min_routes)]
    return sub.sort_values(["major_score", "route_count"], ascending=False).head(n)


def top_airports_by_city(
    df_in: pd.DataFrame,
    iso_country: str,
    city_text: str,
    n: int = 10,
    min_routes: int = 5,
    contains: bool = True,
    allowed_types=("large_airport", "medium_airport", "small_airport"),
) -> pd.DataFrame:
    iso_country = str(iso_country).upper().strip()
    city_text_lc = str(city_text).strip().lower()
    sub = df_in[df_in["iso_country"].astype("string").str.upper().str.strip() == iso_country].copy()
    sub = sub[sub["type"].isin(allowed_types)]
    muni = sub["municipality"].astype("string").fillna("").str.lower()
    if contains:
        sub = sub[muni.str.contains(city_text_lc, na=False)]
    else:
        sub = sub[muni.eq(city_text_lc)]
    sub = sub[sub["route_count"] >= int(min_routes)]
    return sub.sort_values(["major_score", "route_count"], ascending=False).head(n)


def build_country_airport_map(
    df_in: pd.DataFrame,
    topk: int = DEFAULT_TOPK_PER_COUNTRY,
    min_routes: int = DEFAULT_MIN_ROUTES,
    primary_types=("large_airport", "medium_airport"),
    fallback_types=("large_airport", "medium_airport", "small_airport"),
    ensure_one: bool = True,
) -> pd.DataFrame:
    df_in = df_in.copy()
    df_in["iso_country"] = df_in["iso_country"].astype("string").str.upper().str.strip()
    countries = sorted([c for c in df_in["iso_country"].dropna().unique() if str(c).strip() != ""])
    rows = []
    for cc in countries:
        sub = df_in[df_in["iso_country"] == cc].copy()
        pick = sub[sub["type"].isin(primary_types) & (sub["route_count"] >= int(min_routes))].sort_values(
            ["major_score", "route_count"], ascending=False
        ).head(int(topk))
        if pick.empty:
            pick = sub[sub["type"].isin(fallback_types) & (sub["route_count"] >= 1)].sort_values(
                ["major_score", "route_count"], ascending=False
            ).head(int(topk))
        if pick.empty:
            pick = sub[sub["type"].isin(fallback_types)].sort_values(
                ["major_score", "route_count"], ascending=False
            ).head(max(1, int(topk)))
        if pick.empty and ensure_one:
            pick = sub.sort_values(["major_score", "route_count"], ascending=False).head(1)
        if not pick.empty:
            rows.append(pick)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=df_in.columns)
    out = out.sort_values(["iso_country", "major_score", "route_count"], ascending=[True, False, False]).reset_index(drop=True)
    return out


if __name__ == "__main__":
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    df = load_and_score()
    out_path = os.path.join(base, "airport_ranked.csv")
    df.to_csv(out_path, index=False)
    print("Saved:", out_path)
    country_top = build_country_airport_map(df, topk=15, min_routes=10, ensure_one=True)
    country_out = os.path.join(base, "country_top_airports.csv")
    country_top.to_csv(country_out, index=False)
    print("Saved:", country_out)
    print("\nTop airports for GB:")
    print(top_airports_by_country(df, "GB", n=10)[["iata_code", "name", "municipality", "type", "route_count", "major_score"]])
