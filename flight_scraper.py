"""
Flight scraper using fast-flights library
Rolling 30-day window: scrape by departure_date, store first_seen.
"""

from fast_flights import FlightData, Passengers, get_flights
from datetime import datetime, timedelta
import time
from multiprocessing import Pool
import random
import urllib.parse

TOP_50_US_AIRPORTS = [
    'ATL', 'DFW', 'DEN', 'ORD', 'LAX', 'CLT', 'MCO', 'LAS', 'PHX', 'MIA',
    'SEA', 'IAH', 'EWR', 'SFO', 'BOS', 'MSP', 'DTW', 'FLL', 'JFK', 'LGA',
    'PHL', 'BWI', 'DCA', 'IAD', 'SAN', 'SLC', 'TPA', 'PDX', 'HNL', 'AUS',
    'MDW', 'BNA', 'DAL', 'RDU', 'STL', 'HOU', 'SJC', 'MCI', 'OAK', 'SAT',
    'RSW', 'IND', 'CMH', 'CVG', 'PIT', 'SMF', 'CLE', 'MKE', 'SNA', 'ANC',
]


def _parse_stops(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def generate_google_flights_url(origin, destination, date):
    base = "https://www.google.com/travel/flights"
    query = f"Flights from {origin} to {destination} on {date}"
    encoded_query = urllib.parse.quote(query)
    return f"{base}?q={encoded_query}"


def scrape_route(args):
    """
    Scrape a single route for a given departure date.
    Args: (origin, destination, departure_date)
    Returns: dict with flight data or None
    """
    origin, destination, departure_date = args

    time.sleep(1 + random.random())

    try:
        result = get_flights(
            flight_data=[
                FlightData(
                    date=departure_date,
                    from_airport=origin,
                    to_airport=destination
                )
            ],
            trip="one-way",
            seat="economy",
            passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0)
        )

        if result and result.flights:
            cheapest = min(result.flights, key=lambda x: float(x.price.replace('$', '').replace(',', '')))
            price = float(cheapest.price.replace('$', '').replace(',', ''))

            return {
                'origin': origin,
                'destination': destination,
                'route': f"{origin}-{destination}",
                'departure_date': departure_date,
                'price': price,
                'currency': 'USD',
                'airline': getattr(cheapest, 'name', None),
                'departure_time': getattr(cheapest, 'departure', None),
                'arrival_time': getattr(cheapest, 'arrival', None),
                'duration': getattr(cheapest, 'duration', None),
                'num_stops': _parse_stops(getattr(cheapest, 'stops', 0)),
                'is_best': getattr(cheapest, 'is_best', False),
                'google_flights_url': generate_google_flights_url(origin, destination, departure_date),
                'first_seen': datetime.now().strftime('%Y-%m-%d'),
            }

        return None

    except Exception as e:
        print(f"Error scraping {origin}-{destination}: {e}")
        return None


def scrape_all_routes(origins, destinations, departure_date, num_workers=5):
    """
    Scrape all route combinations for one departure date.
    """
    routes = []
    for origin in origins:
        for dest in destinations:
            if origin != dest:
                routes.append((origin, dest, departure_date))

    print(f"Scraping {len(routes)} routes for {departure_date} with {num_workers} workers...")
    with Pool(processes=num_workers) as pool:
        results = pool.map(scrape_route, routes)
    valid = [r for r in results if r is not None]
    print(f"Successfully scraped {len(valid)}/{len(routes)} routes")
    return valid


def scrape_baseline(origins, destinations, num_workers=5):
    """
    INITIAL BASELINE: Scrape all routes for next 31 days (today through +30).
    Run once on first setup. Takes ~9 hours for 50×50×31.
    """
    print("=" * 60)
    print("BASELINE SCRAPE - Building 30-day window")
    print("=" * 60)

    all_flights = []
    for days_ahead in range(0, 31):
        departure_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        print(f"\nScraping day {days_ahead + 1}/31: {departure_date}")
        flights = scrape_all_routes(origins, destinations, departure_date, num_workers)
        all_flights.extend(flights)
        print(f"Progress: {len(all_flights)} total flights collected")

    print(f"\n✓ Baseline complete: {len(all_flights)} flights")
    return all_flights


def scrape_incremental(origins, destinations, num_workers=5):
    """
    DAILY INCREMENTAL: Refresh today + add new +30 day.
    Run every day after baseline. ~5,000 routes, ~34 min for 50×50.
    """
    print("=" * 60)
    print("INCREMENTAL SCRAPE - Daily refresh")
    print("=" * 60)

    all_flights = []

    today = (datetime.now()).strftime('%Y-%m-%d')
    print(f"\n1. Refreshing TODAY: {today}")
    all_flights.extend(scrape_all_routes(origins, destinations, today, num_workers))

    new_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    print(f"\n2. Adding NEW +30 date: {new_date}")
    all_flights.extend(scrape_all_routes(origins, destinations, new_date, num_workers))

    print(f"\n✓ Incremental complete: {len(all_flights)} flights")
    return all_flights


if __name__ == "__main__":
    test_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
    results = scrape_all_routes(['JFK', 'LAX'], ['MIA', 'ORD'], test_date, num_workers=2)
    print(f"Scraped {len(results)} flights")
