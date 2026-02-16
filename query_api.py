"""
Example queries for retrieving flight data
"""

from db_manager import FlightDatabase


def get_cheapest_flights_from_jfk():
    """Example: Get cheapest flights from JFK today"""
    db = FlightDatabase()
    db.connect()

    today_deals = db.get_cheapest_from_origin('JFK', time_filter='today')

    print("Cheapest flights from JFK today:")
    for i, flight in enumerate(today_deals[:10], 1):
        print(f"{i}. {flight['destination']}: ${flight['price']:.2f} ({flight.get('departure_date', '')} {flight['airline'] or 'N/A'})")

    db.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    get_cheapest_flights_from_jfk()
