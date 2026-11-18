"""
Headless scrape + categorize entrypoint for cron/CI.

Uses the httpx-only KaufdaJsonScraper (no Playwright) so it runs cheaply on
GitHub Actions. Steps:

  1. Scrape all keywords from kaufDA's JSON-embedded brochure pages.
  2. Upsert into Supabase `offers` + append a `price_history` row per offer
     whose price changed (or wasn't recorded in the last HISTORY_RESAMPLE_DAYS).
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
from datetime import datetime, timedelta, timezone

from providers.supabase_client import get_supabase
from scraper.kaufda_json import KaufdaJsonScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_scrape")

BATCH = 50

# kaufDA prices change with the weekly brochure, not daily. Storing the same
# price every day multiplied price_history ~7x and filled the 500 MB free plan.
# A row is written when the price changes, or at least once per this window so
# the 90-day deal score keeps enough observations.
HISTORY_RESAMPLE_DAYS = 7


def _price_key(row: dict) -> tuple:
    """Comparable (price, loyalty_price) — numeric strings and floats alike."""
    def norm(v):
        if v is None:
            return None
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return v
    return (norm(row.get("price")), norm(row.get("loyalty_price")))


def select_history_rows(returned: list[dict], recent: list[dict], now: datetime) -> list[dict]:
    """price_history rows worth storing for one upserted chunk.

    `recent` = existing price_history rows (offer_id, price, loyalty_price,
    observed_at) from the last HISTORY_RESAMPLE_DAYS for these offers. An offer
    is skipped when its current price was already recorded in that window.
    Offers without a price are never recorded (nothing to chart).
    """
    seen: dict[str, set] = {}
    for r in recent:
        seen.setdefault(r.get("offer_id"), set()).add(_price_key(r))

    rows = []
    for r in returned:
        if r.get("price") is None and r.get("loyalty_price") is None:
            continue
        if _price_key(r) in seen.get(r["id"], set()):
            continue
        rows.append({
            "offer_id":         r["id"],
            "external_id":      r["external_id"],
            "price":            r.get("price"),
            "loyalty_price":    r.get("loyalty_price"),
            "original_price":   r.get("original_price"),
            "discount_percent": r.get("discount_percent"),
            "store":            r.get("store"),
            "category":         r.get("category"),
            "observed_at":      now.isoformat(),
        })
    return rows


def _recent_history(sb, offer_ids: list[str], now: datetime) -> list[dict]:
    """Recent price_history rows for these offers; [] on error (then we just write)."""
    if not offer_ids:
        return []
    since = (now - timedelta(days=HISTORY_RESAMPLE_DAYS)).isoformat()
    try:
        res = (
            sb.table("price_history")
            .select("offer_id, price, loyalty_price")
            .in_("offer_id", offer_ids)
            .gte("observed_at", since)
            .execute()
        )
        return res.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("price_history lookup failed (%s) — writing all rows", exc)
        return []


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


def upsert_offers(offers: list[dict]) -> list[dict]:
    """Batch-upsert offers + price_history. Returns successfully upserted rows."""
    sb = get_supabase()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    history_written = 0
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

    all_returned: list[dict] = []
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
        all_returned.extend(returned)
        # price_history for the deal score — only when the price is new
        # (see HISTORY_RESAMPLE_DAYS). offer_id comes from the upsert response.
        recent = _recent_history(sb, [r["id"] for r in returned], now_dt)
        history_rows = select_history_rows(returned, recent, now_dt)
        if history_rows:
            try:
                sb.table("price_history").insert(history_rows).execute()
                history_written += len(history_rows)
            except Exception as exc:  # noqa: BLE001
                logger.warning("price_history insert failed for chunk: %s", exc)
        logger.info("  upserted %d/%d", len(all_returned), len(rows))
    if failed:
        logger.error("Failed to upsert %d/%d rows", failed, len(rows))
    logger.info(
        "price_history: %d new rows (%d unchanged prices skipped)",
        history_written, len(all_returned) - history_written,
    )
    return all_returned


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

    returned = upsert_offers(offers)
    logger.info("Upserted %d offers into Supabase", len(returned))
    if not returned:
        logger.error("Every upsert chunk failed — treating run as failed.")
        return 1

    # Drain embedding_queue so bulk inserts don't leave semantic search empty.
    try:
        from providers.embeddings import drain_embedding_queue
        drained = 0
        # Cap loops so a huge backlog can't blow the Actions budget.
        for _ in range(20):
            n = drain_embedding_queue(limit=200)
            drained += n
            if n == 0:
                break
        if drained:
            logger.info("Drained %d embedding_queue jobs", drained)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding drain skipped: %s", exc)

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
