"""
Landmark-specific search terms for city/country images.
Use these for Pixabay (https://pixabay.com/images/search/...) or when prompting AI for images.
Rule: Use UNIQUE LANDMARK + city/country to avoid wrong/generic results.

When manually fetching from Pixabay:
  https://pixabay.com/images/search/{encoded_search}/
  e.g. https://pixabay.com/images/search/burj%20khalifa%20dubai/
"""

# Airport code -> Pixabay-style search (landmark + city, specific = accurate)
LANDMARK_SEARCHES = {
    # Middle East
    "DXB": "burj khalifa dubai skyline",
    "AUH": "sheikh zayed mosque abu dhabi",
    "DOH": "doha skyline corniche",
    "BAH": "bahrain world trade center manama",
    # Asia
    "SIN": "marina bay sands singapore",
    "HKG": "hong kong victoria harbour skyline",
    "NRT": "tokyo skyline mount fuji",
    "HND": "tokyo tower shibuya",
    "ICN": "seoul namsan tower",
    "BKK": "grand palace bangkok wat",
    "KUL": "petronas towers kuala lumpur",
    "DEL": "india gate delhi",
    "BOM": "gateway of india mumbai",
    # Europe
    "LHR": "big ben london parliament",
    "CDG": "eiffel tower paris trocadero",
    "FRA": "frankfurt skyline main tower",
    "AMS": "amsterdam canals dutch houses",
    "BCN": "sagrada familia barcelona",
    "MAD": "royal palace madrid spain",
    "FCO": "colosseum rome italy",
    "DUB": "trinity college dublin",
    "EDI": "edinburgh castle scotland",
    "VIE": "st stephens cathedral vienna",
    "BRU": "grand place brussels belgium",
    "ZRH": "zurich lake swiss alps",
    # North America
    "YYZ": "cn tower toronto",
    "YVR": "vancouver stanley park",
    "YUL": "old montreal harbour",
    "MEX": "angel independence mexico city",
    # Oceania
    "SYD": "sydney opera house harbour bridge",
    "MEL": "flinders street melbourne",
    "AKL": "sky tower auckland new zealand",
    # Africa
    "JNB": "soweto towers johannesburg",
    "CPT": "table mountain cape town",
    "CAI": "pyramids giza cairo",
    # Central/South America
    "PTY": "panama canal",
    "SJO": "san jose costa rica volcano",
    "GRU": "sao paulo skyline brazil",
    "EZE": "buenos aires obelisco",
}

# Manual Pixabay search URLs (use when API has no good results):
# https://pixabay.com/images/search/burj%20khalifa%20dubai/
# https://pixabay.com/images/search/eiffel%20tower%20paris/

# Airport code -> ISO 3166-1 alpha-2 country code (for flag fallback: flagcdn.com/w80/{cc}.png)
AIRPORT_TO_COUNTRY = {
    "DXB": "ae", "AUH": "ae", "DOH": "qa", "BAH": "bh",
    "SIN": "sg", "HKG": "hk", "NRT": "jp", "HND": "jp", "ICN": "kr",
    "BKK": "th", "KUL": "my", "DEL": "in", "BOM": "in",
    "LHR": "gb", "CDG": "fr", "FRA": "de", "AMS": "nl", "BCN": "es",
    "MAD": "es", "FCO": "it", "DUB": "ie", "EDI": "gb", "VIE": "at",
    "BRU": "be", "ZRH": "ch",
    "YYZ": "ca", "YVR": "ca", "YUL": "ca", "MEX": "mx",
    "SYD": "au", "MEL": "au", "AKL": "nz",
    "JNB": "za", "CPT": "za", "CAI": "eg",
    "PTY": "pa", "SJO": "cr",
    # US
    "ATL": "us", "DFW": "us", "DEN": "us", "ORD": "us", "LAX": "us",
    "MIA": "us", "SFO": "us", "SEA": "us", "JFK": "us", "LGA": "us",
    "TLV": "il",
}
