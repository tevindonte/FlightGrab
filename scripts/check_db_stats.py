"""
Check FlightGrab DB stats: flights, routes, destinations, last scrape.
Run: python scripts/check_db_stats.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from db_manager import FlightDatabase


def main():
    db = FlightDatabase()
    db.connect()

    cursor = db.conn.cursor()

    # Total flights (future dates)
    cursor.execute(
        "SELECT COUNT(*) FROM current_prices WHERE departure_date >= CURRENT_DATE"
    )
    total_flights = cursor.fetchone()[0]

    # Distinct routes
    cursor.execute(
        "SELECT COUNT(DISTINCT origin || '-' || destination) FROM current_prices WHERE departure_date >= CURRENT_DATE"
    )
    total_routes = cursor.fetchone()[0]

    # Distinct destinations (what the UI shows as "destinations")
    cursor.execute(
        """
        SELECT COUNT(DISTINCT destination) FROM current_prices
        WHERE departure_date >= CURRENT_DATE AND price > 0
        """
    )
    distinct_destinations = cursor.fetchone()[0]

    # Distinct origins
    cursor.execute(
        "SELECT COUNT(DISTINCT origin) FROM current_prices WHERE departure_date >= CURRENT_DATE"
    )
    distinct_origins = cursor.fetchone()[0]

    # Updated today (last 24h)
    cursor.execute(
        "SELECT COUNT(*) FROM current_prices WHERE DATE(last_updated) = CURRENT_DATE"
    )
    updated_today = cursor.fetchone()[0]

    # Updated yesterday (last night's scrape)
    cursor.execute(
        "SELECT COUNT(*) FROM current_prices WHERE DATE(last_updated) = CURRENT_DATE - INTERVAL '1 day'"
    )
    updated_yesterday = cursor.fetchone()[0]

    # Destinations by country (international vs US)
    cursor.execute(
        """
        SELECT destination, COUNT(*) as cnt
        FROM current_prices
        WHERE departure_date >= CURRENT_DATE AND price > 0
        GROUP BY destination
        ORDER BY cnt DESC
        """
    )
    dest_counts = cursor.fetchall()

    cursor.close()
    db.close()

    print("=" * 60)
    print("FlightGrab Database Stats")
    print("=" * 60)
    print(f"Total flights (future dates):     {total_flights:,}")
    print(f"Distinct routes:                  {total_routes:,}")
    print(f"Distinct destinations:            {distinct_destinations}")
    print(f"Distinct origins:                 {distinct_origins}")
    print()
    print(f"Updated today:                    {updated_today:,}")
    print(f"Updated yesterday (last night):   {updated_yesterday:,}")
    print()
    print("Top 20 destinations by flight count:")
    for dest, cnt in dest_counts[:20]:
        print(f"  {dest}: {cnt} flights")
    print()

    # Destinations that may lack images (not in US state map or country flag map)
    US_STATES = {
        'ATL', 'DFW', 'DEN', 'ORD', 'LAX', 'CLT', 'MCO', 'LAS', 'PHX', 'MIA',
        'SEA', 'IAH', 'EWR', 'SFO', 'BOS', 'MSP', 'DTW', 'FLL', 'JFK', 'LGA',
        'PHL', 'BWI', 'DCA', 'IAD', 'SAN', 'SLC', 'TPA', 'PDX', 'HNL', 'AUS',
        'MDW', 'BNA', 'DAL', 'RDU', 'STL', 'HOU', 'SJC', 'MCI', 'OAK', 'SAT',
        'RSW', 'IND', 'CMH', 'CVG', 'PIT', 'SMF', 'CLE', 'MKE', 'SNA', 'ANC',
    }
    FLAG_COUNTRIES = {
        'DXB', 'AUH', 'DOH', 'SIN', 'HKG', 'NRT', 'HND', 'ICN', 'BKK', 'KUL',
        'DEL', 'BOM', 'LHR', 'CDG', 'FRA', 'AMS', 'BCN', 'MAD', 'FCO', 'DUB',
        'EDI', 'MUC', 'ZRH', 'VIE', 'ATH', 'IST', 'CPH', 'OSL', 'ARN', 'PRG',
        'BUD', 'WAW', 'LIS', 'BRU', 'YYZ', 'YVR', 'YUL', 'MEX', 'GRU', 'EZE',
        'SYD', 'MEL', 'BNE', 'AKL', 'JNB', 'CPT', 'CAI', 'PTY', 'SJO', 'TLV',
    }
    all_dests = [d for d, _ in dest_counts]
    missing_image = [d for d in all_dests if d not in US_STATES and d not in FLAG_COUNTRIES]
    if missing_image:
        print("Destinations that may need images (add to AIRPORT_TO_COUNTRY in app.js):")
        for d in missing_image:
            print(f"  {d}")
        print()

    print("Note: UI dedupes by city name (JFK+LGA+EWR -> 1 card). API limit raised to 150.")


if __name__ == "__main__":
    main()
