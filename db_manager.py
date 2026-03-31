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
                booking_url TEXT,
                google_booking_url TEXT,
                first_seen DATE NOT NULL,
                last_updated TIMESTAMP DEFAULT NOW(),

                UNIQUE(origin, destination, departure_date)
            );
        """)
        for col_name in ["booking_url", "google_booking_url"]:
            try:
                cursor.execute(
                    "SELECT 1 FROM information_schema.columns "
                    f"WHERE table_name='current_prices' AND column_name=%s",
                    (col_name,),
                )
                if not cursor.fetchone():
                    cursor.execute(f"ALTER TABLE current_prices ADD COLUMN {col_name} TEXT")
            except Exception:
                pass
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                origin VARCHAR(3) NOT NULL,
                destination VARCHAR(3) NOT NULL,
                target_price DECIMAL(10,2) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                last_notified_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            );
        """)
        for col in ['user_id', 'origin', 'destination', 'is_active']:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_alerts_{col} ON price_alerts({col});")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_flights (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                origin VARCHAR(3) NOT NULL,
                destination VARCHAR(3) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_flights(user_id);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_date_preferences (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL UNIQUE,
                date_from DATE,
                date_to DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_date_prefs ON user_date_preferences(user_id);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL UNIQUE,
                status VARCHAR(20) DEFAULT 'free',
                stripe_customer_id VARCHAR(255),
                stripe_subscription_id VARCHAR(255),
                current_period_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON user_subscriptions(user_id);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                first_name VARCHAR(255) DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        for col_name, col_def in [
            ("verified", "BOOLEAN DEFAULT FALSE"),
            ("verification_token", "VARCHAR(255)"),
            ("verification_sent_at", "TIMESTAMP"),
        ]:
            try:
                cursor.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name=%s",
                    (col_name,),
                )
                if not cursor.fetchone():
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

        self.conn.commit()
        cursor.close()
        print("Tables created")

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
             google_flights_url, booking_url, google_booking_url, first_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                booking_url = COALESCE(EXCLUDED.booking_url, current_prices.booking_url),
                google_booking_url = COALESCE(EXCLUDED.google_booking_url, current_prices.google_booking_url),
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
                f.get('google_flights_url'), f.get('booking_url'),
                f.get('google_booking_url'),
                f['first_seen']
            )
            for f in flights
        ]

        execute_batch(cursor, query, values)
        self.conn.commit()
        cursor.close()
        print(f"Inserted/updated {len(flights)} flights")

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
        print("Created daily snapshot")

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
        print(f"Cleaned up {deleted} departed flights")

    def get_cheapest_from_origin(self, origin, time_filter='today', client_date=None, specific_date=None, date_from=None, date_to=None):
        """
        Get cheapest flights from an origin. specific_date or date_from+date_to override time_filter.
        """
        cursor = self.conn.cursor()
        base_date = "CURRENT_DATE"
        if client_date and time_filter in ('today', 'tomorrow') and len(client_date) == 10:
            try:
                from datetime import datetime
                datetime.strptime(client_date, "%Y-%m-%d")
                base_date = f"'{client_date}'::date"
            except ValueError:
                pass
        if specific_date and len(specific_date) == 10:
            try:
                from datetime import datetime
                datetime.strptime(specific_date, "%Y-%m-%d")
                cond = f"departure_date = '{specific_date}'::date"
            except ValueError:
                cond = f"departure_date = {base_date}"
        elif date_from and date_to and len(date_from) == 10 and len(date_to) == 10:
            try:
                from datetime import datetime
                datetime.strptime(date_from, "%Y-%m-%d")
                datetime.strptime(date_to, "%Y-%m-%d")
                cond = f"departure_date BETWEEN '{date_from}'::date AND '{date_to}'::date"
            except ValueError:
                date_conditions = {'today': f"departure_date = {base_date}", 'tomorrow': f"departure_date = {base_date} + INTERVAL '1 day'",
                    'weekend': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '3 days'",
                    'week': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '7 days'",
                    'month': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '30 days'",
                    'flexible': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '30 days'"}
                cond = date_conditions.get(time_filter, date_conditions['today'])
        else:
            date_conditions = {
                'today': f"departure_date = {base_date}",
                'tomorrow': f"departure_date = {base_date} + INTERVAL '1 day'",
                'weekend': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '3 days'",
                'week': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '7 days'",
                'month': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '30 days'",
                'flexible': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '30 days'"
            }
            cond = date_conditions.get(time_filter, date_conditions['today'])

        cursor.execute(f"""
            SELECT DISTINCT ON (destination)
                destination, price, airline, departure_date,
                departure_time, COALESCE(booking_url, google_booking_url, google_flights_url), duration, num_stops,
                google_booking_url
            FROM current_prices
            WHERE origin = %s AND {cond} AND price > 0
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
                    'google_booking_url': r[8] if len(r) > 8 else None,
                }
                for r in rows
            ],
            key=lambda x: x['price']
        )[:50]

    def get_cheapest_from_all_origins(self, time_filter='week', client_date=None, specific_date=None, date_from=None, date_to=None):
        """
        Get cheapest flight to each destination from ANY origin.
        specific_date: single date. date_from+date_to: range. Otherwise use time_filter.
        """
        cursor = self.conn.cursor()
        base_date = "CURRENT_DATE"
        if client_date and time_filter in ('today', 'tomorrow') and len(client_date) == 10:
            try:
                from datetime import datetime
                datetime.strptime(client_date, "%Y-%m-%d")
                base_date = f"'{client_date}'::date"
            except ValueError:
                pass
        date_conditions = {
            'today': f"departure_date = {base_date}",
            'tomorrow': f"departure_date = {base_date} + INTERVAL '1 day'",
            'weekend': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '3 days'",
            'week': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '7 days'",
            'month': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '30 days'",
            'flexible': f"departure_date BETWEEN {base_date} AND {base_date} + INTERVAL '30 days'"
        }
        if specific_date and len(specific_date) == 10:
            try:
                from datetime import datetime
                datetime.strptime(specific_date, "%Y-%m-%d")
                cond = f"departure_date = '{specific_date}'::date"
            except ValueError:
                cond = date_conditions.get(time_filter, date_conditions['week'])
        elif date_from and date_to and len(date_from) == 10 and len(date_to) == 10:
            try:
                from datetime import datetime
                datetime.strptime(date_from, "%Y-%m-%d")
                datetime.strptime(date_to, "%Y-%m-%d")
                cond = f"departure_date BETWEEN '{date_from}'::date AND '{date_to}'::date"
            except ValueError:
                cond = date_conditions.get(time_filter, date_conditions['week'])
        else:
            cond = date_conditions.get(time_filter, date_conditions['week'])

        cursor.execute(f"""
            SELECT DISTINCT ON (destination)
                origin, destination, price, airline, departure_date,
                departure_time, COALESCE(booking_url, google_booking_url, google_flights_url), duration, num_stops,
                google_booking_url
            FROM current_prices
            WHERE {cond} AND price > 0
            ORDER BY destination, price ASC
        """)
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
                    'origin': r[0],
                    'destination': r[1],
                    'price': float(r[2]),
                    'airline': r[3],
                    'departure_date': r[4].isoformat() if r[4] else None,
                    'departure_time': r[5],
                    'booking_url': r[6],
                    'duration': r[7] if len(r) > 7 else None,
                    'num_stops': _num_stops(r[8]) if len(r) > 8 else 0,
                    'google_booking_url': r[9] if len(r) > 9 else None,
                }
                for r in rows
            ],
            key=lambda x: x['price']
        )[:150]

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

    def get_route_flights(self, origin: str, destination: str, limit: int = 100, departure_date=None):
        """
        Get flights for a specific route (origin -> destination).
        Returns list of flight dicts with price, date, airline, etc.
        If departure_date is set (YYYY-MM-DD), only rows for that date are returned.
        """
        cursor = self.conn.cursor()
        date_filter = ""
        params = [origin.upper(), destination.upper()]
        if departure_date:
            date_filter = " AND departure_date = %s"
            params.append(departure_date)
        params.append(limit)
        cursor.execute(
            f"""
            SELECT origin, destination, departure_date, price, num_stops, airline,
                   duration, departure_time, COALESCE(booking_url, google_booking_url, google_flights_url),
                   google_booking_url
            FROM current_prices
            WHERE origin = %s AND destination = %s
            AND departure_date >= CURRENT_DATE AND price > 0
            {date_filter}
            ORDER BY price ASC, departure_date ASC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        cursor.close()

        def _num_stops(n):
            if n is None:
                return 0
            try:
                return int(n)
            except (TypeError, ValueError):
                return 0

        def _date_iso(d):
            if d is None:
                return None
            if hasattr(d, "isoformat"):
                return d.isoformat()
            return str(d)

        return [
            {
                "origin": r[0],
                "destination": r[1],
                "date": _date_iso(r[2]),
                "price": float(r[3]) if r[3] is not None else 0.0,
                "stops": _num_stops(r[4]),
                "airline": r[5] or "",
                "duration": r[6] or "",
                "departure_time": r[7] or "",
                "booking_url": r[8],
                "google_booking_url": r[9],
            }
            for r in rows
        ]

    def get_all_routes(self):
        """
        Get all unique (origin, destination) pairs with future flights.
        For sitemap and route page discovery.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT origin, destination
            FROM current_prices
            WHERE departure_date >= CURRENT_DATE AND price > 0
            ORDER BY origin, destination
        """)
        rows = cursor.fetchall()
        cursor.close()
        return [{"origin": r[0], "destination": r[1]} for r in rows]

    def get_related_routes(self, origin: str, destination: str, limit: int = 6):
        """
        Get related routes: other destinations from same origin, other origins to same destination.
        For "Related flight searches" section.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            (SELECT origin, destination FROM current_prices
             WHERE origin = %s AND destination != %s AND departure_date >= CURRENT_DATE AND price > 0
             GROUP BY origin, destination ORDER BY MIN(price) ASC LIMIT %s)
            UNION ALL
            (SELECT origin, destination FROM current_prices
             WHERE origin != %s AND destination = %s AND departure_date >= CURRENT_DATE AND price > 0
             GROUP BY origin, destination ORDER BY MIN(price) ASC LIMIT %s)
            """,
            (origin.upper(), destination.upper(), limit // 2, origin.upper(), destination.upper(), limit // 2),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [{"origin": r[0], "destination": r[1]} for r in rows]

    def get_all_flights_paginated(
        self,
        page: int = 1,
        limit: int = 50,
        origin: str = None,
        destination: str = None,
        max_price: float = None,
        date_from: str = None,
        date_to: str = None,
        date_exact: str = None,
        stops: int = None,
        airlines: list = None,
        time_of_day: str = None,
        sort_by: str = "price",
        sort_order: str = "asc",
    ):
        """
        Get all flights with filters and pagination. For /deals page.
        stops: exact match (0=nonstop, 1=1 stop, etc.). airlines: list of airline names.
        time_of_day: morning|afternoon|evening|night.
        Returns: (flights list, total count)
        """
        cursor = self.conn.cursor()
        conditions = ["departure_date >= CURRENT_DATE", "price > 0"]
        params = []
        if origin:
            conditions.append("origin = %s")
            params.append(origin.upper()[:3])
        if destination:
            conditions.append("destination = %s")
            params.append(destination.upper()[:3])
        if max_price is not None:
            conditions.append("price <= %s")
            params.append(float(max_price))
        if date_exact and len(date_exact) == 10:
            try:
                datetime.strptime(date_exact, "%Y-%m-%d")
                conditions.append("departure_date = %s::date")
                params.append(date_exact)
            except ValueError:
                pass
        elif date_from and date_to and len(date_from) == 10 and len(date_to) == 10:
            try:
                datetime.strptime(date_from, "%Y-%m-%d")
                datetime.strptime(date_to, "%Y-%m-%d")
                conditions.append("departure_date BETWEEN %s::date AND %s::date")
                params.extend([date_from, date_to])
            except ValueError:
                pass
        if stops is not None:
            conditions.append("num_stops = %s")
            params.append(int(stops))
        if airlines and len(airlines) > 0:
            placeholders = ", ".join(["%s"] * len(airlines))
            conditions.append(f"airline IN ({placeholders})")
            params.extend([a.strip() for a in airlines if a and a.strip()])
        if time_of_day and time_of_day in ("morning", "afternoon", "evening", "night"):
            h_expr = "NULLIF(substring(departure_time from '([0-9]{1,2}):'), '')::int"
            am_expr = "(departure_time ~ ' AM' OR departure_time ~ 'AM ')"
            pm_expr = "(departure_time ~ ' PM' OR departure_time ~ 'PM ')"
            hour_conds = {
                "morning": f"({am_expr} AND {h_expr} BETWEEN 5 AND 11)",
                "afternoon": f"(({pm_expr} AND {h_expr} BETWEEN 1 AND 5) OR ({pm_expr} AND {h_expr} = 12))",
                "evening": f"({pm_expr} AND {h_expr} BETWEEN 6 AND 9)",
                "night": f"(({pm_expr} AND {h_expr} IN (10,11)) OR ({am_expr} AND {h_expr} IN (12,1,2,3,4)))",
            }
            conditions.append("(departure_time ~ '[0-9]{1,2}:[0-9]{2} *[AP]M' AND " + hour_conds[time_of_day] + ")")
        where_clause = " AND ".join(conditions)
        sort_col = "price" if sort_by == "price" else sort_by
        if sort_col not in ("price", "departure_date", "origin", "destination", "num_stops"):
            sort_col = "price"
        order = "ASC" if sort_order.lower() == "asc" else "DESC"
        order_clause = f"ORDER BY {sort_col} {order}, departure_date ASC"
        offset = (page - 1) * limit
        params_ext = params + [limit, offset]
        cursor.execute(
            f"""
            SELECT origin, destination, departure_date, price, num_stops, airline,
                   duration, departure_time, google_booking_url, booking_url
            FROM current_prices
            WHERE {where_clause}
            {order_clause}
            LIMIT %s OFFSET %s
            """,
            params_ext,
        )
        rows = cursor.fetchall()
        count_params = params
        cursor.execute(
            f"SELECT COUNT(*) FROM current_prices WHERE {where_clause}",
            count_params,
        )
        total = cursor.fetchone()[0]
        cursor.close()

        def _num_stops(n):
            if n is None:
                return 0
            try:
                return int(n)
            except (TypeError, ValueError):
                return 0

        flights = [
            {
                "origin": r[0],
                "destination": r[1],
                "date": r[2].isoformat() if r[2] else None,
                "price": float(r[3]),
                "stops": _num_stops(r[4]),
                "airline": r[5] or "",
                "duration": r[6] or "",
                "departure_time": r[7] or "",
                "google_booking_url": r[8],
                "booking_url": r[9],
            }
            for r in rows
        ]
        return flights, total

    def get_all_deals_facets(
        self,
        origin: str = None,
        destination: str = None,
        max_price: float = None,
        date_from: str = None,
        date_to: str = None,
        date_exact: str = None,
        stops: int = None,
        airlines: list = None,
        time_of_day: str = None,
    ):
        """
        Get available filter options (airlines, stops, time) for the current filter set.
        Only returns values that exist in the filtered dataset.
        """
        cursor = self.conn.cursor()
        conditions = ["departure_date >= CURRENT_DATE", "price > 0"]
        params = []
        if origin:
            conditions.append("origin = %s")
            params.append(origin.upper()[:3])
        if destination:
            conditions.append("destination = %s")
            params.append(destination.upper()[:3])
        if max_price is not None:
            conditions.append("price <= %s")
            params.append(float(max_price))
        if date_exact and len(date_exact) == 10:
            try:
                datetime.strptime(date_exact, "%Y-%m-%d")
                conditions.append("departure_date = %s::date")
                params.append(date_exact)
            except ValueError:
                pass
        elif date_from and date_to and len(date_from) == 10 and len(date_to) == 10:
            try:
                datetime.strptime(date_from, "%Y-%m-%d")
                datetime.strptime(date_to, "%Y-%m-%d")
                conditions.append("departure_date BETWEEN %s::date AND %s::date")
                params.extend([date_from, date_to])
            except ValueError:
                pass
        if stops is not None:
            conditions.append("num_stops = %s")
            params.append(int(stops))
        if airlines and len(airlines) > 0:
            placeholders = ", ".join(["%s"] * len(airlines))
            conditions.append(f"airline IN ({placeholders})")
            params.extend([a.strip() for a in airlines if a and a.strip()])
        if time_of_day and time_of_day in ("morning", "afternoon", "evening", "night"):
            h_expr = "NULLIF(substring(departure_time from '([0-9]{1,2}):'), '')::int"
            am_expr = "(departure_time ~ ' AM' OR departure_time ~ 'AM ')"
            pm_expr = "(departure_time ~ ' PM' OR departure_time ~ 'PM ')"
            hc = {
                "morning": f"({am_expr} AND {h_expr} BETWEEN 5 AND 11)",
                "afternoon": f"(({pm_expr} AND {h_expr} BETWEEN 1 AND 5) OR ({pm_expr} AND {h_expr} = 12))",
                "evening": f"({pm_expr} AND {h_expr} BETWEEN 6 AND 9)",
                "night": f"(({pm_expr} AND {h_expr} IN (10,11)) OR ({am_expr} AND {h_expr} IN (12,1,2,3,4)))",
            }
            conditions.append("(departure_time ~ '[0-9]{1,2}:[0-9]{2} *[AP]M' AND " + hc[time_of_day] + ")")
        where_clause = " AND ".join(conditions)

        airlines_facet = []
        cursor.execute(
            f"""
            SELECT airline, COUNT(*)::int
            FROM current_prices
            WHERE {where_clause} AND airline IS NOT NULL AND airline != ''
            GROUP BY airline
            ORDER BY COUNT(*) DESC
            LIMIT 50
            """,
            params,
        )
        for r in cursor.fetchall():
            airlines_facet.append({"value": r[0], "count": r[1]})

        stops_facet = []
        cursor.execute(
            f"""
            SELECT num_stops, COUNT(*)::int
            FROM current_prices
            WHERE {where_clause}
            GROUP BY num_stops
            ORDER BY num_stops ASC
            """,
            params,
        )
        for r in cursor.fetchall():
            n = r[0] if r[0] is not None else 0
            try:
                n = int(n)
            except (TypeError, ValueError):
                n = 0
            label = "Nonstop" if n == 0 else ("1 stop" if n == 1 else f"{n} stops")
            stops_facet.append({"value": n, "label": label, "count": r[1]})

        time_facet = []
        try:
            cursor.execute(
                f"""
                WITH parsed AS (
                    SELECT
                        CASE
                            WHEN departure_time ~ '[0-9]{{1,2}}:[0-9]{{2}} *[AP]M' THEN
                                CASE
                                    WHEN departure_time ~ 'PM' AND NULLIF(substring(departure_time from '([0-9]{{1,2}}):'), '')::int != 12
                                        THEN NULLIF(substring(departure_time from '([0-9]{{1,2}}):'), '')::int + 12
                                    WHEN departure_time ~ 'AM' AND NULLIF(substring(departure_time from '([0-9]{{1,2}}):'), '')::int = 12
                                        THEN 0
                                    ELSE NULLIF(substring(departure_time from '([0-9]{{1,2}}):'), '')::int
                                END
                            ELSE NULL
                        END as hr
                    FROM current_prices
                    WHERE {where_clause}
                )
                SELECT
                    CASE
                        WHEN hr >= 5 AND hr < 12 THEN 'morning'
                        WHEN hr >= 12 AND hr < 17 THEN 'afternoon'
                        WHEN hr >= 17 AND hr < 21 THEN 'evening'
                        WHEN hr IS NOT NULL THEN 'night'
                        ELSE NULL
                    END as bucket,
                    COUNT(*)
                FROM parsed
                WHERE hr IS NOT NULL
                GROUP BY 1
                ORDER BY 1
                """,
                params,
            )
            label_map = {"morning": "Morning (5am-12pm)", "afternoon": "Afternoon (12pm-5pm)", "evening": "Evening (5pm-9pm)", "night": "Night (9pm-5am)"}
            for r in cursor.fetchall():
                if r[0]:
                    time_facet.append({"value": r[0], "label": label_map.get(r[0], r[0]), "count": r[1]})
        except Exception:
            pass

        cursor.close()
        return {"airlines": airlines_facet, "stops": stops_facet, "time_of_day": time_facet}

    def get_cheap_destinations(self, max_price: float = 100, limit: int = 20):
        """
        Get destinations where min price is <= max_price, with origin count.
        For "Where can you fly for under $X?" widget.
        Returns: list of {destination, min_price, origin_count}
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT destination, MIN(price)::float as min_price,
                   COUNT(DISTINCT origin)::int as origin_count
            FROM current_prices
            WHERE departure_date >= CURRENT_DATE AND price > 0 AND price <= %s
            GROUP BY destination
            ORDER BY min_price ASC
            LIMIT %s
            """,
            (float(max_price), limit),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "destination": r[0],
                "min_price": round(float(r[1]), 2),
                "origin_count": r[2],
            }
            for r in rows
        ]

    def get_price_drops(self, limit: int = 10):
        """
        Get routes where current min price is significantly below route average.
        Heuristic: compare MIN(price) to AVG(price) per route.
        Returns: list of {origin, destination, current_price, avg_price, drop_percent}
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            WITH route_stats AS (
                SELECT origin, destination,
                       MIN(price)::float as current_price,
                       AVG(price)::float as avg_price,
                       COUNT(*) as flight_count
                FROM current_prices
                WHERE departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
                AND price > 0
                GROUP BY origin, destination
                HAVING COUNT(*) >= 3
            )
            SELECT origin, destination, current_price, avg_price,
                   ((avg_price - current_price) / NULLIF(avg_price, 0) * 100)::float as drop_pct
            FROM route_stats
            WHERE avg_price > 0 AND ((avg_price - current_price) / avg_price * 100) > 15
            ORDER BY drop_pct DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "origin": r[0],
                "destination": r[1],
                "current_price": float(r[2]),
                "avg_price": float(r[3]),
                "drop_percent": round(float(r[4] or 0), 1),
            }
            for r in rows
        ]

    def get_popular_routes(self, limit: int = 10):
        """
        Get routes with most flight options (proxy for popularity).
        Later: track actual user searches/clicks.
        Returns: list of {origin, destination, min_price, flight_count}
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT origin, destination,
                   MIN(price)::float as min_price,
                   COUNT(*)::int as flight_count
            FROM current_prices
            WHERE departure_date >= CURRENT_DATE AND price > 0
            GROUP BY origin, destination
            ORDER BY flight_count DESC, min_price ASC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "origin": r[0],
                "destination": r[1],
                "min_price": round(float(r[2]), 2),
                "flight_count": r[3],
            }
            for r in rows
        ]

    def get_calendar_destinations(self, origin: str, limit: int = 200):
        """
        Get all destinations from an origin with their minimum price.
        Returns: list of {code, minPrice}
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT destination, MIN(price)::float as min_price
            FROM current_prices
            WHERE origin = %s AND departure_date >= CURRENT_DATE AND price > 0
            GROUP BY destination
            ORDER BY min_price ASC
            LIMIT %s
        """, (origin.upper(), limit))
        rows = cursor.fetchall()
        cursor.close()
        return [{"code": r[0], "minPrice": round(float(r[1]), 2)} for r in rows]

    def get_price_calendar(
        self, origin: str, destination: str,
        days: int = 30,
        date_from: str = None,
        date_to: str = None,
    ):
        """
        Get cheapest price per date for a route.
        Use days, or date_from+date_to for a range.
        Returns: list of {date, price, airline, duration, num_stops, google_booking_url}
        """
        cursor = self.conn.cursor()
        if date_from and date_to:
            try:
                from datetime import datetime
                datetime.strptime(date_from, "%Y-%m-%d")
                datetime.strptime(date_to, "%Y-%m-%d")
                date_cond = "departure_date BETWEEN %s::date AND %s::date"
                params = (origin.upper(), destination.upper(), date_from, date_to)
            except ValueError:
                date_cond = "departure_date >= CURRENT_DATE AND departure_date <= CURRENT_DATE + %s"
                params = (origin.upper(), destination.upper(), days)
        else:
            date_cond = "departure_date >= CURRENT_DATE AND departure_date <= CURRENT_DATE + %s"
            params = (origin.upper(), destination.upper(), days)
        cursor.execute(f"""
            SELECT DISTINCT ON (departure_date)
                departure_date,
                price,
                airline,
                duration,
                num_stops,
                google_booking_url
            FROM current_prices
            WHERE origin = %s AND destination = %s
            AND {date_cond}
            AND price > 0
            ORDER BY departure_date, price ASC
        """, params)
        rows = cursor.fetchall()
        cursor.close()

        def _num_stops(n):
            if n is None:
                return 0
            try:
                return int(n)
            except (TypeError, ValueError):
                return 0

        return [
            {
                'date': r[0].isoformat() if r[0] else None,
                'price': float(r[1]),
                'airline': r[2],
                'duration': r[3],
                'num_stops': _num_stops(r[4]),
                'google_booking_url': r[5],
            }
            for r in rows
        ]

    def get_return_flights(self, origin: str, destination: str, outbound_date: str, min_days: int = 2, max_days: int = 30, limit: int = 20):
        """
        Get available return flights (reverse direction: destination -> origin).
        For round-trip: outbound is A->B, return is B->A.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT origin, destination, price, airline, departure_date,
                   departure_time, duration, num_stops,
                   COALESCE(google_booking_url, booking_url) as booking_url,
                   google_booking_url
            FROM current_prices
            WHERE origin = %s AND destination = %s
            AND departure_date >= %s::date + %s
            AND departure_date <= %s::date + %s
            AND price > 0
            ORDER BY price ASC, departure_date ASC
            LIMIT %s
        """, (destination, origin, outbound_date, min_days, outbound_date, max_days, limit))
        rows = cursor.fetchall()
        cursor.close()

        def _num_stops(n):
            if n is None:
                return 0
            try:
                return int(n)
            except (TypeError, ValueError):
                return 0

        return [
            {
                'origin': r[0],
                'destination': r[1],
                'price': float(r[2]),
                'airline': r[3],
                'departure_date': r[4].isoformat() if r[4] else None,
                'departure_time': r[5],
                'duration': r[6],
                'num_stops': _num_stops(r[7]),
                'booking_url': r[8],
                'google_booking_url': r[9] if len(r) > 9 else None,
            }
            for r in rows
        ]

    def search_route(self, origin, destination, time_filter='today'):
        """Get best price for a route in the given departure window."""
        cursor = self.conn.cursor()
        date_conditions = {
            'today': "departure_date = CURRENT_DATE",
            'tomorrow': "departure_date = CURRENT_DATE + INTERVAL '1 day'",
            'weekend': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'",
            'week': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'",
            'month': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'",
            'flexible': "departure_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'"
        }
        cond = date_conditions.get(time_filter, date_conditions['today'])
        cursor.execute(f"""
            SELECT origin, destination, route, departure_date, price, currency, airline,
                   departure_time, arrival_time, duration, num_stops,
                   COALESCE(booking_url, google_booking_url, google_flights_url),
                   google_booking_url
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
            'booking_url': row[11],
            'google_booking_url': row[12] if len(row) > 12 else None,
        }

    def create_user(
        self,
        user_id: str,
        email: str,
        password_hash: str,
        first_name: str = "",
        verification_token: str = None,
    ) -> bool:
        """Create user. Returns False if email already exists."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO users (id, email, password_hash, first_name, verification_token, verification_sent_at)
                   VALUES (%s, %s, %s, %s, %s, CASE WHEN %s IS NOT NULL THEN NOW() ELSE NULL END)""",
                (
                    user_id,
                    email.lower().strip(),
                    password_hash,
                    (first_name or "").strip()[:100],
                    verification_token,
                    verification_token,
                ),
            )
            self.conn.commit()
            return True
        except psycopg2.IntegrityError:
            self.conn.rollback()
            return False
        finally:
            cursor.close()

    def get_user_by_email(self, email: str):
        """Get user by email. Returns dict with id, email, password_hash, first_name, verified or None."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, email, password_hash, first_name, COALESCE(verified, TRUE) FROM users WHERE LOWER(email) = LOWER(%s)",
                (email.strip(),),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
        if not row:
            return None
        return {
            "id": row[0],
            "email": row[1],
            "password_hash": row[2],
            "first_name": row[3] or "",
            "verified": bool(row[4]) if len(row) > 4 else True,
        }

    def get_user_by_id(self, user_id: str):
        """Get user by id. Returns dict with id, email, first_name, verified or None."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, email, first_name, COALESCE(verified, TRUE) FROM users WHERE id = %s",
                (user_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
        if not row:
            return None
        return {
            "id": row[0],
            "email": row[1],
            "first_name": row[2] or "",
            "verified": bool(row[3]) if len(row) > 3 else True,
        }

    def get_user_by_verification_token(self, token: str):
        """Find user by verification token if not expired (24h). Returns dict or None."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """SELECT id, email FROM users
                   WHERE verification_token = %s
                   AND verification_sent_at > NOW() - INTERVAL '24 hours'""",
                (token,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
        if not row:
            return None
        return {"id": row[0], "email": row[1]}

    def verify_user(self, user_id: str) -> bool:
        """Mark user as verified. Returns True if updated."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET verified = TRUE, verification_token = NULL WHERE id = %s",
                (user_id,),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()

    def get_subscription_status(self, user_id: str):
        """Return is_premium, alert_count, alert_limit. Free users limited to 5 alerts."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT status FROM user_subscriptions WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        is_premium = row and row[0] == "active"
        cursor.execute(
            "SELECT COUNT(*) FROM price_alerts WHERE user_id = %s AND is_active = TRUE",
            (user_id,),
        )
        alert_count = cursor.fetchone()[0]
        alert_limit = 999999 if is_premium else 5
        cursor.close()
        return {
            "is_premium": is_premium,
            "alert_count": alert_count,
            "alert_limit": alert_limit,
            "can_add_more": alert_count < alert_limit,
        }

    def upsert_subscription(
        self,
        user_id: str,
        status: str = "active",
        stripe_customer_id: str = None,
        stripe_subscription_id: str = None,
        current_period_end: datetime = None,
    ):
        """Create or update user subscription (for Stripe webhooks)."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_subscriptions (user_id, status, stripe_customer_id, stripe_subscription_id, current_period_end, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                status = EXCLUDED.status,
                stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, user_subscriptions.stripe_customer_id),
                stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, user_subscriptions.stripe_subscription_id),
                current_period_end = COALESCE(EXCLUDED.current_period_end, user_subscriptions.current_period_end),
                updated_at = NOW()
            """,
            (user_id, status, stripe_customer_id, stripe_subscription_id, current_period_end),
        )
        self.conn.commit()
        cursor.close()

    def subscribe_alert(self, user_id: str, email: str, origin: str, destination: str, target_price: float) -> int:
        """Insert price alert, return alert id. Raises ValueError if free user at alert limit."""
        status = self.get_subscription_status(user_id)
        if not status["can_add_more"]:
            raise ValueError("ALERT_LIMIT_REACHED")
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO price_alerts (user_id, email, origin, destination, target_price)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, email, origin.upper(), destination.upper(), target_price),
        )
        alert_id = cursor.fetchone()[0]
        self.conn.commit()
        cursor.close()
        return alert_id

    def get_user_alerts(self, user_id: str):
        """Get active alerts for a user."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, origin, destination, target_price, created_at, last_notified_at
            FROM price_alerts
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "id": r[0],
                "origin": r[1],
                "destination": r[2],
                "target_price": float(r[3]),
                "created_at": r[4].isoformat() if r[4] else None,
                "last_notified_at": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]

    def get_triggered_alerts(self):
        """
        Get active alerts where current price is at or below target.
        Join with cheapest current price per route. Exclude recently notified.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            WITH cheapest AS (
                SELECT DISTINCT ON (origin, destination)
                    origin, destination, price, departure_date,
                    COALESCE(google_booking_url, booking_url) as booking_url
                FROM current_prices
                WHERE departure_date >= CURRENT_DATE AND price > 0
                ORDER BY origin, destination, price ASC
            )
            SELECT a.id, a.email, a.origin, a.destination, a.target_price,
                   c.price, c.departure_date, c.booking_url
            FROM price_alerts a
            JOIN cheapest c ON a.origin = c.origin AND a.destination = c.destination
            WHERE a.is_active = TRUE AND c.price <= a.target_price
            AND (a.last_notified_at IS NULL OR a.last_notified_at < CURRENT_DATE)
            ORDER BY c.price ASC
        """)
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "id": r[0],
                "email": r[1],
                "origin": r[2],
                "destination": r[3],
                "target_price": float(r[4]),
                "current_price": float(r[5]),
                "departure_date": r[6].isoformat() if r[6] else None,
                "booking_url": r[7],
            }
            for r in rows
        ]

    def mark_alert_notified(self, alert_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE price_alerts SET last_notified_at = NOW() WHERE id = %s",
            (alert_id,),
        )
        self.conn.commit()
        cursor.close()

    def deactivate_alert(self, alert_id: int, user_id: str) -> bool:
        """Deactivate alert if it belongs to user. Return True if updated."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE price_alerts SET is_active = FALSE WHERE id = %s AND user_id = %s",
            (alert_id, user_id),
        )
        updated = cursor.rowcount > 0
        self.conn.commit()
        cursor.close()
        return updated

    def save_flight(self, user_id: str, origin: str, destination: str, notes: str = None) -> int:
        """Save a route for the user. Returns saved_flight id. Skips insert if already saved."""
        origin, destination = origin.upper(), destination.upper()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id FROM saved_flights
            WHERE user_id = %s AND origin = %s AND destination = %s
            """,
            (user_id, origin, destination),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.close()
            return existing[0]
        cursor.execute(
            """
            INSERT INTO saved_flights (user_id, origin, destination, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, origin, destination, notes or ""),
        )
        row = cursor.fetchone()
        saved_id = row[0] if row else 0
        self.conn.commit()
        cursor.close()
        return saved_id

    def get_user_saved_flights(self, user_id: str):
        """Get saved flights for a user."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, origin, destination, notes, created_at
            FROM saved_flights
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return [
            {
                "id": r[0],
                "origin": r[1],
                "destination": r[2],
                "notes": (r[3] or "").strip() or None,
                "created_at": r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]

    def delete_saved_flight(self, saved_id: int, user_id: str) -> bool:
        """Delete saved flight if it belongs to user."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM saved_flights WHERE id = %s AND user_id = %s",
            (saved_id, user_id),
        )
        deleted = cursor.rowcount > 0
        self.conn.commit()
        cursor.close()
        return deleted

    def get_user_date_preferences(self, user_id: str):
        """Get saved date range for user. Returns {date_from, date_to} or None."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT date_from, date_to FROM user_date_preferences WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row or (not row[0] and not row[1]):
            return None
        return {
            "date_from": row[0].isoformat() if row[0] else None,
            "date_to": row[1].isoformat() if row[1] else None,
        }

    def save_user_date_preferences(self, user_id: str, date_from: str, date_to: str) -> bool:
        """Save preferred date range for user."""
        if not date_from or not date_to or len(date_from) != 10 or len(date_to) != 10:
            return False
        try:
            from datetime import datetime
            datetime.strptime(date_from, "%Y-%m-%d")
            datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            return False
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_date_preferences (user_id, date_from, date_to, updated_at)
            VALUES (%s, %s::date, %s::date, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                date_from = EXCLUDED.date_from,
                date_to = EXCLUDED.date_to,
                updated_at = NOW()
            """,
            (user_id, date_from, date_to),
        )
        self.conn.commit()
        cursor.close()
        return True

    def close(self):
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    db = FlightDatabase()
    db.connect()
    db.create_tables()
    print("Database ready")
    db.close()
