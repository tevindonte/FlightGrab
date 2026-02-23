"""
Airport code to city name mapping for route pages and sitemap.
Used for SEO-friendly display and URL slugs.
"""

# Code -> City (matches app.js AIRPORT_CITIES for consistency)
CODE_TO_CITY = {
    "ATL": "Atlanta", "DFW": "Dallas", "DEN": "Denver", "ORD": "Chicago",
    "LAX": "Los Angeles", "CLT": "Charlotte", "MCO": "Orlando", "LAS": "Las Vegas",
    "PHX": "Phoenix", "MIA": "Miami", "SEA": "Seattle", "IAH": "Houston",
    "EWR": "Newark", "SFO": "San Francisco", "BOS": "Boston", "MSP": "Minneapolis",
    "DTW": "Detroit", "FLL": "Fort Lauderdale", "JFK": "New York", "LGA": "New York",
    "PHL": "Philadelphia", "BWI": "Baltimore", "DCA": "Washington", "IAD": "Washington",
    "SAN": "San Diego", "SLC": "Salt Lake City", "TPA": "Tampa", "PDX": "Portland",
    "HNL": "Honolulu", "AUS": "Austin", "MDW": "Chicago", "BNA": "Nashville",
    "DAL": "Dallas", "RDU": "Raleigh", "STL": "St. Louis", "HOU": "Houston",
    "SJC": "San Jose", "MCI": "Kansas City", "OAK": "Oakland", "SAT": "San Antonio",
    "RSW": "Fort Myers", "IND": "Indianapolis", "CMH": "Columbus", "CVG": "Cincinnati",
    "PIT": "Pittsburgh", "SMF": "Sacramento", "CLE": "Cleveland", "MKE": "Milwaukee",
    "SNA": "Santa Ana", "ANC": "Anchorage",
    "DXB": "Dubai", "AUH": "Abu Dhabi", "DOH": "Doha", "SIN": "Singapore",
    "HKG": "Hong Kong", "NRT": "Tokyo", "HND": "Tokyo", "ICN": "Seoul",
    "BKK": "Bangkok", "KUL": "Kuala Lumpur", "LHR": "London", "CDG": "Paris",
    "ORY": "Paris", "FRA": "Frankfurt", "AMS": "Amsterdam", "BCN": "Barcelona",
    "MAD": "Madrid", "FCO": "Rome", "DUB": "Dublin", "EDI": "Edinburgh",
    "MEX": "Mexico City", "MUC": "Munich", "ZRH": "Zurich", "VIE": "Vienna",
    "ATH": "Athens", "IST": "Istanbul", "CPH": "Copenhagen", "OSL": "Oslo",
    "ARN": "Stockholm", "PRG": "Prague", "BUD": "Budapest", "WAW": "Warsaw",
    "LIS": "Lisbon", "BRU": "Brussels", "YYZ": "Toronto", "YVR": "Vancouver",
    "YUL": "Montreal", "YTZ": "Toronto", "SYD": "Sydney", "MEL": "Melbourne",
    "AKL": "Auckland", "BNE": "Brisbane", "GRU": "São Paulo", "EZE": "Buenos Aires",
    "JNB": "Johannesburg", "CPT": "Cape Town", "CAI": "Cairo", "TLV": "Tel Aviv",
    "DEL": "Delhi", "BOM": "Mumbai", "SJO": "San Jose", "PTY": "Panama City",
    "FAO": "Faro", "OPO": "Porto", "NAP": "Naples", "MXP": "Milan",
    "AGP": "Málaga", "PMI": "Palma de Mallorca", "SVQ": "Seville", "VLC": "Valencia",
    "BIO": "Bilbao", "SCL": "Santiago", "BOG": "Bogotá", "CUN": "Cancún",
    "GIG": "Rio de Janeiro", "COR": "Córdoba", "CNS": "Cairns", "PER": "Perth",
    "ADL": "Adelaide", "DUR": "Durban", "NBO": "Nairobi", "ADD": "Addis Ababa",
    "MNL": "Manila", "SGN": "Ho Chi Minh City", "GVA": "Geneva", "CRL": "Charleroi",
    "NCE": "Nice", "LYS": "Lyon", "HAM": "Hamburg", "STR": "Stuttgart",
    "DUS": "Düsseldorf", "CGN": "Cologne", "BHX": "Birmingham", "MAN": "Manchester",
    "LPL": "Liverpool", "NCL": "Newcastle", "NAS": "Nassau", "PUJ": "Punta Cana",
    "MBJ": "Montego Bay", "SXM": "St. Maarten",
}


def get_city_name(code: str) -> str:
    """Return city name for airport code, or the code itself if unknown."""
    if not code:
        return ""
    return CODE_TO_CITY.get(code.upper(), code)


def route_slug(origin: str, destination: str) -> str:
    """Generate URL slug: ATL-to-MIA (uppercase codes for consistency)."""
    o = (origin or "").upper()[:3]
    d = (destination or "").upper()[:3]
    return f"{o}-to-{d}" if o and d else ""


def parse_route_slug(slug: str) -> tuple[str | None, str | None]:
    """
    Parse route slug 'ATL-to-MIA' or 'atl-to-mia' into (origin, destination).
    Returns (None, None) if invalid.
    """
    if not slug or "-to-" not in slug:
        return None, None
    parts = slug.strip().upper().split("-TO-")
    if len(parts) != 2:
        return None, None
    origin, dest = parts[0].strip(), parts[1].strip()
    if len(origin) == 3 and len(dest) == 3:
        return origin, dest
    return None, None
