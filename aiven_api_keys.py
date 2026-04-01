"""
Aiven PostgreSQL: API keys for Python package / Pro booking access.

Set ``AIVEN_DATABASE_URL`` (Service URI) on Render. If unset, API key DB features are skipped
and booking auth falls back to ``FLIGHTGRAB_BOOKING_API_KEYS`` only.

Expects tables ``users``, ``user_subscriptions`` (and optionally ``users.is_premium``).
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from typing import Any, List, Optional

import bcrypt
import psycopg2


def get_aiven_dsn() -> Optional[str]:
    return os.getenv("AIVEN_DATABASE_URL") or os.getenv("AIVEN_POSTGRES_URL")


def connect():
    dsn = get_aiven_dsn()
    if not dsn:
        return None
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://") :]
    return psycopg2.connect(dsn)


def create_api_keys_table() -> None:
    """Idempotent: create api_keys if missing."""
    conn = connect()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                key_hash TEXT NOT NULL,
                key_prefix VARCHAR(32) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                last_used_at TIMESTAMP,
                revoked_at TIMESTAMP
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_prefix_active "
            "ON api_keys(key_prefix) WHERE revoked_at IS NULL;"
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _user_has_active_entitlement(conn, user_id: str) -> bool:
    """Premium via user_subscriptions.status = active or users.is_premium."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT status FROM user_subscriptions WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row and row[0] == "active":
            return True
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'is_premium'"
        )
        if cur.fetchone():
            cur.execute("SELECT is_premium FROM users WHERE id = %s", (user_id,))
            r2 = cur.fetchone()
            return bool(r2 and r2[0])
    except Exception:
        return False
    finally:
        cur.close()
    return False


def verify_api_key(raw_key: Optional[str]) -> bool:
    """
    Validate X-API-Key: bcrypt match + non-revoked + active subscription / premium.
    Updates last_used_at on success.
    """
    if not raw_key or not str(raw_key).strip():
        return False
    raw_key = str(raw_key).strip()
    conn = connect()
    if not conn:
        return False
    prefix = raw_key[:12] if len(raw_key) >= 12 else raw_key
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, key_hash FROM api_keys
            WHERE revoked_at IS NULL AND key_prefix = %s
            """,
            (prefix,),
        )
        rows = cur.fetchall()
        cur.close()
        for key_id, user_id, key_hash in rows:
            try:
                h = key_hash.encode("utf-8") if isinstance(key_hash, str) else key_hash
                if not bcrypt.checkpw(raw_key.encode("utf-8"), h):
                    continue
                if not _user_has_active_entitlement(conn, user_id):
                    continue
                cu = conn.cursor()
                try:
                    cu.execute(
                        "UPDATE api_keys SET last_used_at = %s WHERE id = %s",
                        (datetime.now(timezone.utc), key_id),
                    )
                    conn.commit()
                finally:
                    cu.close()
                return True
            except Exception:
                continue
        return False
    finally:
        conn.close()


def create_key_for_user(user_id: str) -> Optional[dict]:
    """
    Insert a new API key. Returns dict with plaintext ``key`` once; only hash is stored.
    """
    conn = connect()
    if not conn:
        return None
    raw = f"fg_live_{secrets.token_urlsafe(32)}"
    prefix = raw[:12]
    key_hash = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO api_keys (user_id, key_hash, key_prefix)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (user_id, key_hash, prefix),
        )
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0],
            "key": raw,
            "key_prefix": prefix,
            "created_at": row[1].isoformat() if row[1] else None,
            "warning": "Save this key now. It will not be shown again.",
        }
    finally:
        cur.close()
        conn.close()


def list_keys_for_user(user_id: str) -> List[dict]:
    conn = connect()
    if not conn:
        return []
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, key_prefix, created_at, last_used_at, revoked_at
            FROM api_keys WHERE user_id = %s ORDER BY created_at DESC
            """,
            (user_id,),
        )
        out: List[dict] = []
        for r in cur.fetchall():
            out.append(
                {
                    "id": r[0],
                    "key_prefix": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                    "last_used_at": r[3].isoformat() if r[3] else None,
                    "revoked": r[4] is not None,
                }
            )
        return out
    finally:
        cur.close()
        conn.close()


def revoke_key(user_id: str, key_id: int) -> bool:
    conn = connect()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE api_keys SET revoked_at = %s
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            """,
            (datetime.now(timezone.utc), key_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        cur.close()
        conn.close()


def is_aiven_premium(user_id: str) -> bool:
    conn = connect()
    if not conn:
        return False
    try:
        return _user_has_active_entitlement(conn, user_id)
    finally:
        conn.close()

