"""Live smoke-test for KaufdaJsonScraper.

Usage:
  python3 tests/live_json_scrape.py [--keywords N] [--write]

--write enables Supabase upsert (uses store_node logic minus analyses).
"""

import argparse
import asyncio
import json
import logging
from collections import Counter
from datetime import datetime, timezone

from providers.supabase_client import get_supabase
from scraper.kaufda_json import KaufdaJsonScraper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", type=int, default=None, help="limit keywords for dry run")
    ap.add_argument("--write", action="store_true", help="upsert offers into Supabase")
    args = ap.parse_args()

    scraper = KaufdaJsonScraper(max_keywords=args.keywords)
    offers, errors = await scraper.scrape_all()
    print(f"\n== {len(offers)} unique offers, {len(errors)} errors ==")
    if errors:
        for e in errors[:5]:
            print(f"  ERR: {e}")

    by_store = Counter(o.get("store") or "?" for o in offers)
    by_cat = Counter(o.get("category") or "?" for o in offers)
    has_discount = sum(1 for o in offers if o.get("discount_percent"))
    has_loyalty = sum(1 for o in offers if o.get("requires_loyalty"))
    print(f"\nStores (top 15): {by_store.most_common(15)}")
    print(f"Top keywords:    {by_cat.most_common(10)}")
    print(f"Offers w/ discount %: {has_discount}")
    print(f"Offers w/ loyalty:    {has_loyalty}")

    print("\nSample offers:")
    for o in offers[:5]:
        compact = {
            "title": o["title"],
            "store": o["store"],
            "price": o["price"],
            "original_price": o["original_price"],
            "discount_percent": o["discount_percent"],
            "valid_to": o["valid_to"],
            "url": o["url"],
            "image_url": (o["image_url"] or "")[:80],
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))

    if not args.write:
        print("\n(dry run; pass --write to upsert into Supabase)")
        return

    def _iso_to_date(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return value[:10]

    sb = get_supabase()
    inserted, errs = 0, 0
    now = datetime.now(timezone.utc).isoformat()
    BATCH = 200
    rows: list[dict] = []
    for offer in offers:
        rows.append({
            "external_id":      offer["external_id"],
            "title":            offer["title"],
            "url":              offer["url"],
            "image_url":        offer.get("image_url"),
            "price":            offer.get("price"),
            "original_price":   offer.get("original_price"),
            "discount_percent": offer.get("discount_percent"),
            "store":            offer.get("store"),
            "category":         offer.get("category"),
            "validity_text":    offer.get("validity_text"),
            "valid_from":       _iso_to_date(offer.get("valid_from")),
            "valid_to":         _iso_to_date(offer.get("valid_to")),
            "is_upcoming":      bool(offer.get("is_upcoming")),
            "is_active":        True,
            "last_seen_at":     now,
            "scraped_at":       offer.get("scraped_at") or now,
        })

    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        try:
            sb.table("offers").upsert(chunk, on_conflict="external_id").execute()
            inserted += len(chunk)
            print(f"  upserted {inserted}/{len(rows)}")
        except Exception as exc:
            errs += len(chunk)
            print(f"upsert batch {i}: {exc}")
    print(f"\nUpserted {inserted}/{len(rows)} ({errs} errors)")


if __name__ == "__main__":
    asyncio.run(main())
