#!/usr/bin/env python3
"""Insert a test offer into Supabase and poll for embedding generation."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")

    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    sb = create_client(url, service_key)
    external_id = "test-offer-1"

    payload = {
        "external_id": external_id,
        "title": "Test Angebot",
        "url": "https://example.com/test-offer-1",
        "store": "Test Store",
        "category": "test",
        "price": 9.99,
        "is_active": True,
        "last_seen_at": "now()",
    }

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["scraped_at"] = now_iso
    payload["last_seen_at"] = now_iso

    print("Upserting test offer...")
    result = sb.table("offers").upsert(payload, on_conflict="external_id").execute()
    rows = result.data or []
    if not rows:
        print("Upsert returned no rows", file=sys.stderr)
        return 1

    offer_id = rows[0]["id"]
    print(f"Inserted/updated offer id: {offer_id}")

    for attempt in range(1, 8):
        res = (
            sb.table("offers")
            .select("id,external_id,title,embedding")
            .eq("external_id", external_id)
            .single()
            .execute()
        )
        row = res.data or {}
        has_embedding = row.get("embedding") is not None
        print(f"Attempt {attempt}: has_embedding={has_embedding}")
        if has_embedding:
            print("Embedding trigger is working.")
            return 0
        time.sleep(3)

    print("Embedding is still null after polling.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
