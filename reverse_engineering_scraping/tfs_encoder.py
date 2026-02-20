# Google Flights "tfs" encoder/decoder + Location resolver (IATA/Name -> Freebase MID "/m/...")
# - Builds Google Flights URLs by constructing protobuf-in-base64url "tfs"
# - Resolves locations via Wikidata (P238 IATA -> P646 Freebase MID)
# - Adds optional sort via "tfu" (best/cheapest)
#
# Notes:
# - Flights SEARCH uses MIDs (/m/...) in dep/arr.
# - EXPLORE (Anywhere) uses a different tfs schema. Best approach is:
#     scrape Explore page -> extract "View flights" links -> those are standard flights tfs.

import base64
import json
import os
import re
import time
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.message_factory import GetMessageClass


# ============================================================
# Base64url helpers
# ============================================================

def b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    return base64.b64decode(s)


def b64url_encode(b: bytes) -> str:
    s = base64.b64encode(b).decode("ascii")
    return s.replace("+", "-").replace("/", "_").rstrip("=")


def extract_param(url: str, key: str) -> str:
    qs = parse_qs(urlparse(url).query)
    v = qs.get(key, [None])[0]
    if not v:
        raise ValueError(f"No '{key}' parameter found in URL.")
    return v


# ============================================================
# Reverse-engineered enums (Flights Search)
# ============================================================

PASSENGER_CODES = {
    "adult": 1,
    "child": 2,
    "infant_lap": 3,
    "infant_seat": 4,
}

CABIN_CODES = {
    "economy": 1,
    "premium": 2,
    "business": 3,
    "first": 4,
    "exclude_economy": 1,
}

TRIP_CODES = {
    "round_trip": 1,
    "one_way": 2,
    "multi_city": 3,
}

TFU_SORT = {
    "best": "EgYIABAAGAA",
    "cheapest": "EgoIABAAGAAgAigB",
}


# ============================================================
# Protobuf schema for Flights Search tfs
# ============================================================

def build_messages():
    fdp = descriptor_pb2.FileDescriptorProto()
    fdp.name = "tfs.proto"
    fdp.syntax = "proto3"

    airport = fdp.message_type.add()
    airport.name = "Airport"
    a1 = airport.field.add()
    a1.name = "kind"
    a1.number = 1
    a1.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    a1.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT32
    a2 = airport.field.add()
    a2.name = "id"
    a2.number = 2
    a2.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    a2.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

    flight = fdp.message_type.add()
    flight.name = "FlightInfo"
    f_date = flight.field.add()
    f_date.name = "date"
    f_date.number = 2
    f_date.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f_date.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    f_dep = flight.field.add()
    f_dep.name = "dep_airport"
    f_dep.number = 13
    f_dep.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f_dep.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    f_dep.type_name = ".Airport"
    f_arr = flight.field.add()
    f_arr.name = "arr_airport"
    f_arr.number = 14
    f_arr.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f_arr.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    f_arr.type_name = ".Airport"

    w16 = fdp.message_type.add()
    w16.name = "Weird16"
    w16f = w16.field.add()
    w16f.name = "x"
    w16f.number = 1
    w16f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    w16f.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT64

    root = fdp.message_type.add()
    root.name = "TfsRoot"

    def add_u32(name, num, repeated=False):
        f = root.field.add()
        f.name = name
        f.number = num
        f.label = (descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
                   if repeated else descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL)
        f.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT32

    add_u32("a", 1)
    add_u32("b", 2)
    r3 = root.field.add()
    r3.name = "flights"
    r3.number = 3
    r3.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    r3.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    r3.type_name = ".FlightInfo"
    add_u32("pax", 8, repeated=True)
    add_u32("cabin", 9)
    add_u32("d", 14)
    r16 = root.field.add()
    r16.name = "w"
    r16.number = 16
    r16.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    r16.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    r16.type_name = ".Weird16"
    add_u32("trip_type", 19)
    add_u32("cabin_filter", 25)

    pool = descriptor_pool.DescriptorPool()
    pool.Add(fdp)
    Airport = GetMessageClass(pool.FindMessageTypeByName("Airport"))
    FlightInfo = GetMessageClass(pool.FindMessageTypeByName("FlightInfo"))
    Weird16 = GetMessageClass(pool.FindMessageTypeByName("Weird16"))
    TfsRoot = GetMessageClass(pool.FindMessageTypeByName("TfsRoot"))
    return Airport, FlightInfo, Weird16, TfsRoot


Airport, FlightInfo, Weird16, TfsRoot = build_messages()


# ============================================================
# Encode / Decode Flights Search tfs
# ============================================================

def make_tfs(
    slices: List[Tuple[str, str, str]],
    adults: int = 1,
    children: int = 0,
    infants_lap: int = 0,
    infants_seat: int = 0,
    cabin: str = "economy",
    trip_type: str = "round_trip",
    a: int = 28,
    b: int = 2,
    airport_kind: int = 2,
    d_field_14: int = 1,
    weird16_x: int = (2**64 - 1),
) -> str:
    if adults < 1:
        raise ValueError("Must have at least 1 adult")
    total_infants = infants_lap + infants_seat
    if total_infants > 2 * adults:
        raise ValueError("Google UI rule: total infants <= 2 * adults")
    if infants_lap > adults:
        raise ValueError("Google UI rule: infants_on_lap <= adults")
    if cabin not in CABIN_CODES:
        raise ValueError(f"Unknown cabin: {cabin}")
    if trip_type not in TRIP_CODES:
        raise ValueError(f"Unknown trip_type: {trip_type}")
    if trip_type == "one_way" and len(slices) != 1:
        raise ValueError("one_way requires exactly 1 slice")
    if trip_type == "round_trip" and len(slices) != 2:
        raise ValueError("round_trip requires exactly 2 slices")
    if trip_type == "multi_city" and len(slices) < 1:
        raise ValueError("multi_city requires at least 1 slice")

    msg = TfsRoot(
        a=a, b=b,
        cabin=CABIN_CODES[cabin],
        trip_type=TRIP_CODES[trip_type],
        d=d_field_14,
        w=Weird16(x=weird16_x),
    )
    pax_list = (
        [PASSENGER_CODES["adult"]] * adults +
        [PASSENGER_CODES["child"]] * children +
        [PASSENGER_CODES["infant_seat"]] * infants_seat +
        [PASSENGER_CODES["infant_lap"]] * infants_lap
    )
    msg.pax.extend(pax_list)
    if cabin != "economy":
        msg.cabin_filter = 1

    for date, from_mid, to_mid in slices:
        msg.flights.append(
            FlightInfo(
                date=date,
                dep_airport=Airport(kind=airport_kind, id=from_mid),
                arr_airport=Airport(kind=airport_kind, id=to_mid),
            )
        )
    return b64url_encode(msg.SerializeToString())


def parse_tfs(url_or_tfs: str) -> "TfsRoot":
    tfs = extract_param(url_or_tfs, "tfs") if (url_or_tfs.startswith("http") or "tfs=" in url_or_tfs) else url_or_tfs.strip()
    raw = b64url_decode(tfs)
    msg = TfsRoot()
    msg.ParseFromString(raw)
    return msg


def summarize_tfs(msg: "TfsRoot") -> dict:
    inv_pax = {v: k for k, v in PASSENGER_CODES.items()}
    pax_counts: Dict[str, int] = {"adult": 0, "child": 0, "infant_lap": 0, "infant_seat": 0}
    for code in list(msg.pax):
        k = inv_pax.get(code, f"unknown_{code}")
        pax_counts[k] = pax_counts.get(k, 0) + 1
    inv_trip = {v: k for k, v in TRIP_CODES.items()}
    trip_name = inv_trip.get(msg.trip_type, f"unknown_{msg.trip_type}")
    inv_cabin = {v: k for k, v in CABIN_CODES.items() if k != "exclude_economy"}
    cabin_name = inv_cabin.get(msg.cabin, f"unknown_{msg.cabin}")
    if int(getattr(msg, "cabin_filter", 0) or 0) == 1 and msg.cabin == 1:
        cabin_name = "exclude_economy"
    slices = []
    for fl in msg.flights:
        slices.append({"date": fl.date, "from": fl.dep_airport.id, "to": fl.arr_airport.id})
    return {
        "a": msg.a, "b": msg.b, "d_field14": msg.d,
        "weird16_x": msg.w.x if msg.HasField("w") else None,
        "trip_type": trip_name, "cabin": cabin_name,
        "cabin_filter": int(getattr(msg, "cabin_filter", 0) or 0),
        "passengers": pax_counts,
        "slices": slices,
    }


def build_flights_url(tfs: str, hl: str = "en", sort: Optional[str] = None) -> str:
    base = "https://www.google.com/travel/flights/search"
    q = {"tfs": tfs, "hl": hl}
    if sort is not None:
        if sort not in TFU_SORT:
            raise ValueError(f"Unknown sort '{sort}'. Use: {list(TFU_SORT.keys())} or None")
        q["tfu"] = TFU_SORT[sort]
    return base + "?" + urlencode(q)


# ============================================================
# Location resolver (Wikidata): IATA / name -> Freebase MID
# ============================================================

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_USER_AGENT = "tfs-mid-resolver/1.0 (colab; contact: none)"
DEFAULT_CACHE_PATH = "./mid_cache.json"


def _safe_get_json(url: str, params: dict, headers: Optional[dict] = None, timeout: int = 20) -> dict:
    h = headers or {}
    resp = requests.get(url, params=params, headers=h, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def load_mid_cache(path: str = DEFAULT_CACHE_PATH) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_mid_cache(cache: dict, path: str = DEFAULT_CACHE_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


_mid_cache = load_mid_cache()


def _cache_get(key: str) -> Optional[str]:
    return _mid_cache.get(key)


def _cache_set(key: str, mid: str) -> None:
    _mid_cache[key] = mid
    save_mid_cache(_mid_cache)


def _sparql_query(query: str) -> dict:
    time.sleep(0.05)
    return _safe_get_json(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={"User-Agent": _USER_AGENT, "Accept": "application/sparql-results+json"},
        timeout=30,
    )


def iata_to_mid_airport(iata: str) -> Optional[str]:
    iata = iata.strip().upper()
    cache_key = f"iata_airport:{iata}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    query = f'''
    SELECT ?mid WHERE {{
      ?item wdt:P238 "{iata}" .
      ?item wdt:P31/wdt:P279* wd:Q1248784 .
      ?item wdt:P646 ?mid .
    }} LIMIT 5
    '''
    data = _sparql_query(query)
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None
    mid = bindings[0]["mid"]["value"]
    _cache_set(cache_key, mid)
    return mid


def iata_to_mid_any(iata: str) -> Optional[str]:
    iata = iata.strip().upper()
    cache_key = f"iata_any:{iata}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    query = f'''
    SELECT ?mid WHERE {{
      ?item wdt:P238 "{iata}" .
      ?item wdt:P646 ?mid .
    }} LIMIT 5
    '''
    data = _sparql_query(query)
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None
    mid = bindings[0]["mid"]["value"]
    _cache_set(cache_key, mid)
    return mid


def name_to_mid(text: str, language: str = "en") -> Optional[str]:
    text = text.strip()
    cache_key = f"name:{language}:{text.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    data = _safe_get_json(
        WIKIDATA_API,
        params={"action": "wbsearchentities", "search": text, "language": language, "format": "json", "limit": 8},
        headers={"User-Agent": _USER_AGENT},
        timeout=20,
    )
    hits = data.get("search", [])
    if not hits:
        return None
    for h in hits:
        qid = h.get("id")
        if not qid:
            continue
        q = f'SELECT ?mid WHERE {{ wd:{qid} wdt:P646 ?mid . }} LIMIT 1'
        d = _sparql_query(q)
        b = d.get("results", {}).get("bindings", [])
        if b:
            mid = b[0]["mid"]["value"]
            _cache_set(cache_key, mid)
            return mid
    return None


def resolve_place_id(x: str) -> str:
    if not x or not str(x).strip():
        raise ValueError("Empty location input")
    s = str(x).strip()
    if s.startswith("/m/"):
        return s
    if re.fullmatch(r"[A-Za-z]{3}", s):
        iata = s.upper()
        mid = iata_to_mid_airport(iata) or iata_to_mid_any(iata)
        if mid:
            return mid
        raise ValueError(f"Could not resolve IATA code '{iata}' to a Freebase MID via Wikidata.")
    mid = name_to_mid(s, language="en")
    if mid:
        return mid
    raise ValueError(f"Could not resolve '{s}' to a Freebase MID via Wikidata search.")


def resolve_many(items: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for x in items:
        out[x] = resolve_place_id(x)
    return out


def build_flights_url_from_iata(
    slices_iata: List[Tuple[str, str, str]],
    adults: int = 1,
    children: int = 0,
    infants_lap: int = 0,
    infants_seat: int = 0,
    cabin: str = "economy",
    trip_type: str = "round_trip",
    sort: Optional[str] = "best",
    hl: str = "en",
    debug: bool = False,
) -> str:
    slices_mid: List[Tuple[str, str, str]] = []
    for date, from_loc, to_loc in slices_iata:
        from_mid = resolve_place_id(from_loc)
        to_mid = resolve_place_id(to_loc)
        if debug:
            print(f"{from_loc}->{from_mid} | {to_loc}->{to_mid} | {date}")
        slices_mid.append((date, from_mid, to_mid))
    tfs = make_tfs(
        slices=slices_mid,
        adults=adults, children=children,
        infants_lap=infants_lap, infants_seat=infants_seat,
        cabin=cabin, trip_type=trip_type,
    )
    return build_flights_url(tfs, hl=hl, sort=sort)


if __name__ == "__main__":
    url = build_flights_url_from_iata(
        slices_iata=[("2026-05-01", "JFK", "SJU"), ("2026-05-07", "SJU", "JFK")],
        adults=1, cabin="economy", trip_type="round_trip", sort="best", debug=True,
    )
    print("\nFlights Search URL:", url)
    print(summarize_tfs(parse_tfs(url)))
    print("\nBulk resolve:", resolve_many(["JFK", "SJU", "BDL", "London"]))
