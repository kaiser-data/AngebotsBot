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
import time
from datetime import datetime, timezone

from providers.supabase_client import get_supabase
from scraper.kaufda_json import KaufdaJsonScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_scrape")

BATCH = 50


def _upsert_chunk(sb, chunk: list[dict], attempt: int = 0) -> list[dict]:
    """Upsert one chunk of offer rows, surviving Postgres statement timeouts.

    Supabase enforces a statement_timeout on the API role; when the table is
    busy, a large multi-row upsert intermittently exceeds it (error 57014) and
    used to kill the whole daily run before any row was written. Strategy:
    retry once after a short pause, then split the chunk in half — halving
    always converges to a statement that fits the budget.
    """
    try:
        res = sb.table("offers").upsert(chunk, on_conflict="external_id").execute()
        return res.data or []
    except Exception as exc:  # noqa: BLE001 — postgrest APIError shape varies
        if attempt == 0:
            logger.warning("Upsert chunk of %d failed (%s) — retrying once", len(chunk), exc)
            time.sleep(3)
            return _upsert_chunk(sb, chunk, attempt=1)
        if len(chunk) > 5:
            logger.warning("Upsert chunk of %d failed again — splitting in half", len(chunk))
            mid = len(chunk) // 2
            return _upsert_chunk(sb, chunk[:mid]) + _upsert_chunk(sb, chunk[mid:])
        raise


def has_column(sb, table: str, column: str) -> bool:
    """Does `table` expose `column` through PostgREST right now?

    The taxonomy columns arrive with migration 010, which is applied by hand.
    Writing them unconditionally would make every upsert fail with PGRST204
    ("column not found in the schema cache") wherever that migration hasn't run
    yet — killing the nightly scrape. Probing once per run keeps the two
    independent: the columns start being populated on their own once the
    migration lands, with no code change or redeploy.
    """
    try:
        sb.table(table).select(column).limit(1).execute()
        return True
    except Exception as exc:  # noqa: BLE001 — postgrest APIError shape varies
        logger.warning(
            "Column %s.%s unavailable (%s) — skipping it this run. "
            "Apply supabase/migrations/010_kaufda_taxonomy.sql to enable it.",
            table, column, exc,
        )
        return False


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
    write_taxonomy = has_column(sb, "offers", "kaufda_category")
    rows: list[dict] = []
    for offer in offers:
        row = {
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
        }
        if write_taxonomy:
            row["kaufda_category"] = offer.get("kaufda_category")
            row["kaufda_category_path"] = offer.get("kaufda_category_path")
        rows.append(row)

    inserted = 0
    failed = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        try:
            returned = _upsert_chunk(sb, chunk)
        except Exception as exc:  # noqa: BLE001
            # One bad chunk must not kill the run — the remaining offers still
            # need their last_seen_at bumped or the dashboard culls them as stale.
            logger.error("Giving up on chunk %d–%d: %s", i, i + len(chunk), exc)
            failed += len(chunk)
            continue
        inserted += len(chunk)
        # Append a price_history row per offer for the dashboard's deal score.
        # We need the offer_id from the upsert response since external_id isn't
        # the PK on price_history.
        history_rows = []
        for r in returned:
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
    if failed:
        logger.error("Failed to upsert %d/%d rows", failed, len(rows))
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
    if upserted == 0:
        logger.error("Every upsert chunk failed — treating run as failed.")
        return 1

    if args.categorize:
        # Lazy-import to keep the dry-run path light.
        from scripts.categorize_offers import (
            fetch_uncategorized,
            categorize_pending_async,
            MODEL_VERSION,
        )

        pending = fetch_uncategorized(
            limit=args.categorize_limit,
            force=False,
            model_version=MODEL_VERSION,
        )
        if pending:
            logger.info(
                "Categorizing %d new offers… (budget: %d/run)",
                len(pending), args.categorize_limit,
            )
            # Already inside the event loop — await directly rather than
            # asyncio.run(), which would error on a running loop.
            written = await categorize_pending_async(pending, with_vision=False)
            logger.info("Categorized %d offers", written)
        else:
            logger.info("Nothing to categorize.")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", type=int, default=None,
                    help="limit keywords (default: all A–Z keywords)")
    ap.add_argument("--categorize", action="store_true",
                    help="after scraping, run the LLM categorizer over new offers")
    ap.add_argument("--categorize-limit", type=int, default=600,
                    help="max offers to classify per run (default 600 — keeps daily "
                         "runs under GitHub Actions' 60-min budget even with a backlog).")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
