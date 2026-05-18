"""
Headless scrape + categorize entrypoint for cron/CI.

Uses the httpx-only KaufdaJsonScraper (no Playwright) so it runs cheaply on
GitHub Actions. Steps:

  1. Scrape all keywords from kaufDA's JSON-embedded brochure pages.
  2. Upsert into Supabase `offers` + append a `price_history` row per offer.
  3. Optionally run the LLM categorizer over newly-seen offers.

Usage:
  python -m scripts.run_scrape                  # scrape only
  python -m scripts.run_scrape --categorize     # scrape, then categorize new offers
  python -m scripts.run_scrape --keywords 50    # smoke-test with first 50 keywords
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from providers.supabase_client import get_supabase
from scraper.kaufda_json import KaufdaJsonScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_scrape")

BATCH = 200


def _iso_to_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return value[:10]


def upsert_offers(offers: list[dict]) -> int:
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for offer in offers:
        rows.append({
            "external_id":      offer["external_id"],
            "title":            offer["title"],
            "url":              offer["url"],
            "image_url":        offer.get("image_url"),
            "price":            offer.get("price"),
            "standard_price":   offer.get("standard_price"),
            "loyalty_price":    offer.get("loyalty_price"),
            "original_price":   offer.get("original_price"),
            "discount_percent": offer.get("discount_percent"),
            "store":            offer.get("store"),
            "category":         offer.get("category"),
            "requires_loyalty": bool(offer.get("requires_loyalty")),
            "loyalty_program":  offer.get("loyalty_program"),
            "price_condition_text": offer.get("price_condition_text"),
            "validity_text":    offer.get("validity_text"),
            "valid_from":       _iso_to_date(offer.get("valid_from")),
            "valid_to":         _iso_to_date(offer.get("valid_to")),
            "is_upcoming":      bool(offer.get("is_upcoming")),
            "is_active":        True,
            "last_seen_at":     now,
            "scraped_at":       offer.get("scraped_at") or now,
        })

    inserted = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        res = sb.table("offers").upsert(chunk, on_conflict="external_id").execute()
        inserted += len(chunk)
        # Append a price_history row per offer for the dashboard's deal score.
        # We need the offer_id from the upsert response since external_id isn't
        # the PK on price_history.
        history_rows = []
        for r in (res.data or []):
            history_rows.append({
                "offer_id":         r["id"],
                "external_id":      r["external_id"],
                "price":            r.get("price"),
                "loyalty_price":    r.get("loyalty_price"),
                "original_price":   r.get("original_price"),
                "discount_percent": r.get("discount_percent"),
                "store":            r.get("store"),
                "category":         r.get("category"),
                "observed_at":      now,
            })
        if history_rows:
            try:
                sb.table("price_history").insert(history_rows).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("price_history insert failed for chunk: %s", exc)
        logger.info("  upserted %d/%d", inserted, len(rows))
    return inserted


async def main_async(args: argparse.Namespace) -> int:
    scraper = KaufdaJsonScraper(max_keywords=args.keywords)
    offers, errors = await scraper.scrape_all()
    logger.info("Scraped %d offers (%d errors)", len(offers), len(errors))
    if errors:
        for e in errors[:5]:
            logger.warning("  ERR: %s", e)

    if not offers:
        logger.warning("No offers scraped — bailing out before upsert.")
        return 1

    upserted = upsert_offers(offers)
    logger.info("Upserted %d offers into Supabase", upserted)

    if args.categorize:
        # Lazy-import to keep the dry-run path light.
        from scripts.categorize_offers import (
            fetch_uncategorized,
            classify_batch,
            upsert_rows,
            chunks,
            BATCH_SIZE,
            MODEL_VERSION,
        )

        pending = fetch_uncategorized(limit=None, force=False, model_version=MODEL_VERSION)
        if pending:
            logger.info("Categorizing %d new offers…", len(pending))
            for i, batch in enumerate(chunks(pending, BATCH_SIZE), start=1):
                try:
                    rows = classify_batch(batch, with_vision=False)
                    upsert_rows(rows)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Batch %d failed: %s", i, exc)
        else:
            logger.info("Nothing to categorize.")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", type=int, default=None,
                    help="limit keywords (default: all A–Z keywords)")
    ap.add_argument("--categorize", action="store_true",
                    help="after scraping, run the LLM categorizer over new offers")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
