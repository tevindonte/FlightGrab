"""
Exercise create / verify / list / revoke against Aiven.

verify_api_key requires an active entitlement: user_subscriptions.status = 'active'
(or users.is_premium). This script ensures minimal users + user_subscriptions rows.

Requires .env.local with AIVEN_DATABASE_URL.

Usage:
  python test_api_keys.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

from aiven_api_keys import (  # noqa: E402
    connect,
    create_api_keys_table,
    create_key_for_user,
    list_keys_for_user,
    revoke_key,
    verify_api_key,
)

# Stable id for local manual tests (not a real auth user unless you align JWT)
TEST_USER_ID = "manual_test_fg_user"


def _ensure_entitlement_schema(conn) -> None:
    """Minimal DDL so verify_api_key can see active subscription (matches app expectations)."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(255) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            first_name VARCHAR(255) DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
    )
    cur.execute(
        """
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
        """
    )
    conn.commit()
    cur.close()


def _seed_test_user(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (id, email, password_hash)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (TEST_USER_ID, f"{TEST_USER_ID}@local.test", "x"),
    )
    cur.execute(
        """
        INSERT INTO user_subscriptions (user_id, status)
        VALUES (%s, 'active')
        ON CONFLICT (user_id) DO UPDATE SET
            status = EXCLUDED.status,
            updated_at = NOW()
        """,
        (TEST_USER_ID,),
    )
    conn.commit()
    cur.close()


def main() -> None:
    print("Setting up schema and test user...\n")
    create_api_keys_table()
    conn = connect()
    if not conn:
        print("FAIL  connect() returned None — set AIVEN_DATABASE_URL")
        sys.exit(1)
    try:
        _ensure_entitlement_schema(conn)
        _seed_test_user(conn)
    finally:
        conn.close()

    print("Testing API key creation...\n")
    try:
        result = create_key_for_user(TEST_USER_ID)
        if not result:
            print("FAIL  create_key_for_user returned None")
            sys.exit(1)
        print(f"OK  Created key prefix: {result['key_prefix']}...")
        print(f"    Full key (use for curl): {result['key']}")
        test_key = result["key"]
        key_id = result["id"]
    except Exception as e:
        print(f"FAIL  Key creation: {e}")
        sys.exit(1)

    print("\nTesting API key verification...\n")
    try:
        ok = verify_api_key(test_key)
        print(f"OK  verify_api_key(good key): {ok}")
        if not ok:
            print("FAIL  Key should validate (check user_subscriptions / users)")
            sys.exit(1)
        bad = verify_api_key("wrong_key")
        print(f"OK  wrong key rejected: {not bad}")
    except Exception as e:
        print(f"FAIL  Verification: {e}")
        sys.exit(1)

    print("\nTesting API key listing...\n")
    try:
        keys = list_keys_for_user(TEST_USER_ID)
        print(f"OK  Found {len(keys)} key(s)")
        for k in keys:
            print(
                f"    - id={k['id']} prefix={k['key_prefix']} "
                f"revoked={k['revoked']}"
            )
    except Exception as e:
        print(f"FAIL  Listing: {e}")
        sys.exit(1)

    print("\nTesting API key revocation...\n")
    try:
        revoked = revoke_key(TEST_USER_ID, key_id)
        if not revoked:
            print("FAIL  revoke_key returned False")
            sys.exit(1)
        print(f"OK  Revoked key id={key_id}")
        after = verify_api_key(test_key)
        print(f"OK  Revoked key rejected: {not after}")
        if after:
            print("FAIL  Revoked key must not verify")
            sys.exit(1)
    except Exception as e:
        print(f"FAIL  Revocation: {e}")
        sys.exit(1)

    print("\nAll API key tests passed.")


if __name__ == "__main__":
    main()
