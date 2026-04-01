"""
Sanity-check local setup before running test_aiven.py / test_api_keys.py.

Usage (from repo root):
  python check_code.py
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
# Same order as app.py; .env.local must override existing shell vars (e.g. PowerShell placeholders).
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

print("Checking configuration...\n")

required_vars = ["AIVEN_DATABASE_URL"]
for var in required_vars:
    if os.getenv(var):
        print(f"OK  {var} is set")
    else:
        print(f"MISSING  {var} is NOT set (copy .env.local.example to .env.local)")

aiven_url = os.getenv("AIVEN_DATABASE_URL", "")
if aiven_url:
    host = urlparse(aiven_url).hostname or ""
    if host in ("", "...", "YOUR_HOST"):
        print(
            "\nWARN  Parsed hostname looks like a placeholder. If you fixed .env.local but still see this,\n"
            "      clear a stale shell variable:  Remove-Item Env:AIVEN_DATABASE_URL -ErrorAction SilentlyContinue\n"
            "      Or use load_dotenv(..., override=True) (this script already does)."
        )
    else:
        print(f"\nOK  Aiven host (from file, after override): {host}")

print("\nChecking imports...\n")

for mod, pip in (("bcrypt", "bcrypt"), ("psycopg2", "psycopg2-binary")):
    try:
        __import__(mod)
        print(f"OK  {mod} installed")
    except ImportError:
        print(f"FAIL  {mod} — pip install {pip}")

try:
    from aiven_api_keys import connect  # noqa: F401

    print("OK  aiven_api_keys imports (connect)")
except ImportError as e:
    print(f"FAIL  aiven_api_keys: {e}")

print("\nChecking files...\n")
for name in ("aiven_api_keys.py", "app.py"):
    p = ROOT / name
    if p.exists():
        print(f"OK  {name} exists")
    else:
        print(f"FAIL  {name} missing")

print("\nDone.")
