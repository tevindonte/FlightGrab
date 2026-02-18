"""
Database operations for Neon PostgreSQL
Rolling 30-day window: current_prices keyed by (origin, destination, departure_date).
"""

import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime, timedelta
import os


class FlightDatabase:
    def __init__(self, connection_string=None):
        self.conn_string = connection_string or os.getenv('DATABASE_URL')
        self.conn = None

    def connect(self):
        if not self.conn_string:
            raise ValueError("DATABASE_URL not set. Use .env or pass connection_string.")
        self.conn = psycopg2.connect(self.conn_string)
        return self.conn

    def reconnect(self):
        """Close existing connection (if any) and open a new one. Use after long idle periods (e.g. after a multi‑minute scrape) to avoid SSL connection closed errors."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        return self.connect()

    def create_tables(self):
        """Create tables if they don't exist (rolling 30-day schema)."""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS current_prices (
                id BIGSERIAL PRIMARY KEY,
                origin VARCHAR(3) NOT NULL,
                destination VARCHAR(3) NOT NULL,
                route VARCHAR(10) NOT NULL,
                departure_date DATE NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'USD',
                airline VARCHAR(50),
                departure_time VARCHAR(30),
                arrival_time VARCHAR(30),
                duration VARCHAR(20),
                num_stops SMALLINT,
                is_best BOOLEAN DEFAULT FALSE,
                google_flights_url TEXT,
                first_seen DATE NOT NULL,
                last_updated TIMESTAMP DEFAULT NOW(),

                UNIQUE(origin, destination, departure_date)
            );
        """)
        for col in ['origin', 'destination', 'route', 'price', 'departure_date', 'last_updated']:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_cp_{col} ON current_prices({col});")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id BIGSERIAL PRIMARY KEY,
                route VARCHAR(10) NOT NULL,
                min_price DECIMAL(10,2) NOT NULL,
                avg_price DECIMAL(10,2),
                num_flights INTEGER,
                snapshot_date DATE NOT NULL,

                UNIQUE(route, snapshot_date)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_history ON price_history(route);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_date ON price_history(snapshot_date);")

        self.conn.commit()
        cursor.close()
        print("✓ Tables created")

    def insert_flights(self, flights):
        """
        Insert or update flight prices (UPSERT).
        Key: (origin, destination, departure_date). first_seen set only on INSERT.
        """
        if not flights:
            return
        cursor = self.conn.cursor()

        query = """
            INSERT INTO current_prices
            (origin, destination, route, departure_date, price, currency, airline,
             departure_time, arrival_time, duration, num_stops, is_best,
             google_flights_url, first_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (origin, destination, departure_date)
            DO UPDATE SET
                price = EXCLUDED.price,
                airline = EXCLUDED.airline,
                departure_time = EXCLUDED.departure_time,
                arrival_time = EXCLUDED.arrival_time,
                duration = EXCLUDED.duration,
                num_stops = EXCLUDED.num_stops,
                is_best = EXCLUDED.is_best,
                google_flights_url = EXCLUDED.google_flights_url,
                last_updated = NOW()
        """

        def _num_stops(v):
            if v is None:
                return 0
            if isinstance(v, int):
                return v
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        values = [
            (
                f['origin'], f['destination'], f['route'], f['departure_date'],
                f['price'], f.get('currency', 'USD'), f.get('airline') or None,
                f.get('departure_time'), f.get('arrival_time'), f.get('duration'),
                _num_stops(f.get('num_stops')), bool(f.get('is_best', False)),
                f['google_flights_url'], f['first_seen']
            )
            for f in flights
        ]

        execute_batch(cursor, query, values)
        self.conn.commit()
        cursor.close()
        print(f"✓ Inserted/updated {len(flights)} flights")

    def create_daily_snapshot(self):
        """Snapshot current prices by route (min/avg/count) for today's date."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO price_history (route, min_price, avg_price, num_flights, snapshot_date)
            SELECT
                route,
                MIN(price) as min_price,
                AVG(price) as avg_price,
                COUNT(*) as num_flights,
                CURRENT_DATE as snapshot_date
            FROM current_prices
            WHERE departure_date >= CURRENT_DATE
            GROUP BY route
            ON CONFLICT (route, snapshot_date) DO UPDATE SET
                min_price = EXCLUDED.min_price,
                avg_price = EXCLUDED.avg_price,
                num_flights = EXCLUDED.num_flights
        """)
        self.conn.commit()
        cursor.close()
        print("✓ Created daily snapshot")

    def cleanup_old_data(self):
        """Remove flights that have already departed (rolling 30-day window)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM current_prices
            WHERE departure_date < CURRENT_DATE
        """)
        deleted = cursor.rowcount
        cursor.execute("""
            DELETE FROM price_history
            WHERE snapshot_date < CURRENT_DATE - INTERVAL '365 days'
        """)
        self.conn.commit()
        cursor.close()
        print(f"✓ Cleaned up {deleted} departed flights")

    def get_cheapest_from_origin(self, origin, time_filter='today'):
        """
        Get cheapest flights from an origin by departure date.
        time_filter: 'today', 'weekend' (3 days), 'week' (7 days), 'month' (30 days)
        """
        cursor = self.conn.cursor()
        date_conditions = {
            'today': "departure_date = CURRENT_DATE",
            'weekend': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'",
            'week': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'",
            'month': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'"
        }
        cond = date_conditions.get(time_filter, date_conditions['today'])

        cursor.execute(f"""
            SELECT DISTINCT ON (destination)
                destination, price, airline, departure_date,
                departure_time, google_flights_url, duration, num_stops
            FROM current_prices
            WHERE origin = %s AND {cond}
            ORDER BY destination, price ASC
        """, (origin,))
        rows = cursor.fetchall()
        cursor.close()

        def _num_stops(n):
            if n is None:
                return 0
            try:
                return int(n)
            except (TypeError, ValueError):
                return 0

        return sorted(
            [
                {
                    'destination': r[0],
                    'price': float(r[1]),
                    'airline': r[2],
                    'departure_date': r[3].isoformat() if r[3] else None,
                    'departure_time': r[4],
                    'booking_url': r[5],
                    'duration': r[6] if len(r) > 6 else None,
                    'num_stops': _num_stops(r[7]) if len(r) > 7 else 0,
                }
                for r in rows
            ],
            key=lambda x: x['price']
        )[:50]

    def get_origins_with_data(self):
        """Return origin codes that have future departure data."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT origin FROM current_prices
            WHERE departure_date >= CURRENT_DATE
            ORDER BY origin
        """)
        rows = cursor.fetchall()
        cursor.close()
        return [r[0] for r in rows]

    def search_route(self, origin, destination, time_filter='today'):
        """Get best price for a route in the given departure window."""
        cursor = self.conn.cursor()
        date_conditions = {
            'today': "departure_date = CURRENT_DATE",
            'weekend': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'",
            'week': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'",
            'month': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'"
        }
        cond = date_conditions.get(time_filter, date_conditions['today'])
        cursor.execute(f"""
            SELECT origin, destination, route, departure_date, price, currency, airline,
                   departure_time, arrival_time, duration, num_stops,
                   google_flights_url
            FROM current_prices
            WHERE origin = %s AND destination = %s AND {cond}
            ORDER BY price ASC
            LIMIT 1
        """, (origin, destination))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        return {
            'origin': row[0],
            'destination': row[1],
            'route': row[2],
            'departure_date': row[3].isoformat() if row[3] else None,
            'price': float(row[4]),
            'currency': row[5],
            'airline': row[6],
            'departure_time': row[7],
            'arrival_time': row[8],
            'duration': row[9],
            'num_stops': row[10],
            'booking_url': row[11]
        }

    def close(self):
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    db = FlightDatabase()
    db.connect()
    db.create_tables()
    print("✓ Database ready")
    db.close()
