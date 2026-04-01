"""
Test Aiven connectivity and api_keys table DDL.

Requires .env.local with AIVEN_DATABASE_URL (see .env.local.example).

Usage:
  python test_aiven.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

from aiven_api_keys import connect, create_api_keys_table  # noqa: E402


def main() -> None:
    print("Testing Aiven connection...\n")

    try:
        conn = connect()
        if not conn:
            print("FAIL  connect() returned None — set AIVEN_DATABASE_URL in .env.local")
            sys.exit(1)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"OK  Connected. PostgreSQL: {version}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"FAIL  Connection: {e}")
        sys.exit(1)

    print("\nTesting table creation...\n")
    try:
        create_api_keys_table()
        print("OK  api_keys table created (or already exists)")
    except Exception as e:
        print(f"FAIL  Table creation: {e}")
        sys.exit(1)

    print("\nAll Aiven smoke tests passed.")


if __name__ == "__main__":
    main()
