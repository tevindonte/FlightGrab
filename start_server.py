"""
Run the API with the same env loading as app.py (.env, then .env.local overrides).

Usage (repo root):
  python start_server.py

Use this if you prefer not to rely on shell env vars; keep secrets in .env.local only.

On Windows, uvicorn --reload must run under ``if __name__ == "__main__"`` so the worker
process does not re-import this module incorrectly.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def main() -> None:
    for key in ("AIVEN_DATABASE_URL", "DATABASE_URL"):
        v = os.environ.get(key)
        if v:
            h = urlparse(v).hostname
            if h in ("...", "YOUR_HOST"):
                del os.environ[key]

    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=True)

    print(f"DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}")
    print(f"AIVEN_DATABASE_URL set: {bool(os.getenv('AIVEN_DATABASE_URL'))}")

    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
