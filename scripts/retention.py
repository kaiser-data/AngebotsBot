"""
Keep the Supabase database under the 500 MB free-plan limit — without losing data.

Two phases, run by the daily GitHub Action around a git push:

  export  Write rows that are past retention to gzipped CSV files plus a
          manifest (exact ids). Nothing is deleted.
          → the workflow commits the files to the `data-archive` branch.
  prune   Delete exactly the rows listed in the manifest, then clear
          embeddings of long-unseen offers and log table sizes.

Deleting only after the archive is pushed means a failed push never loses rows:
the prune step doesn't run, and the next day exports the same rows again.

What is retained in the database:
  price_history  last HISTORY_DAYS days (deal score uses 90)
  offers         seen in the last OFFER_DAYS days (older ones are inactive,
                 their links are dead; deleting cascades only history rows that
                 are older still, which were archived first — see below)
  embeddings     cleared for offers unseen for EMBEDDING_DAYS (existing RPC)

OFFER_DAYS >= HISTORY_DAYS on purpose: an offer unseen for OFFER_DAYS has no
history newer than that, so all of it was already exported by the history pass.

Usage:
  python -m scripts.retention export --out archive_out
  python -m scripts.retention prune  --manifest archive_out/manifest.json
  python -m scripts.retention report
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("retention")

HISTORY_DAYS = 120
OFFER_DAYS = 120
EMBEDDING_DAYS = 21

PAGE = 1000
# Bound each run so a large first backlog is worked off over several days
# instead of one run that hits the Actions timeout.
MAX_ROWS_PER_RUN = 150_000
DELETE_CHUNK = 200

HISTORY_COLUMNS = [
    "id", "offer_id", "external_id", "price", "loyalty_price", "original_price",
    "discount_percent", "store", "category", "observed_at",
]
# No embedding / vision blobs — the archive is for price analysis, not search.
OFFER_COLUMNS = [
    "id", "external_id", "title", "store", "category", "kaufda_category",
    "kaufda_category_path", "price", "original_price", "discount_percent",
    "url", "image_url", "valid_from", "valid_to", "first_seen_at", "last_seen_at",
]


def cutoffs(now: datetime) -> dict[str, str]:
    assert OFFER_DAYS >= HISTORY_DAYS, "offers must outlive their history (cascade)"
    return {
        "history_before": (now - timedelta(days=HISTORY_DAYS)).isoformat(),
        "offers_before": (now - timedelta(days=OFFER_DAYS)).isoformat(),
    }


def write_csv_gz(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in columns})


def read_csv_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _existing_columns(sb, table: str, wanted: list[str]) -> list[str]:
    """Columns from `wanted` that exist (taxonomy columns depend on migration 010)."""
    cols = []
    for c in wanted:
        try:
            sb.table(table).select(c).limit(1).execute()
            cols.append(c)
        except Exception:  # noqa: BLE001
            logger.info("column %s.%s missing — not archived", table, c)
    return cols


def _fetch_older(sb, table: str, columns: list[str], ts_col: str, before: str) -> list[dict]:
    """Rows with ts_col < before, ordered by id, capped at MAX_ROWS_PER_RUN."""
    rows: list[dict] = []
    while len(rows) < MAX_ROWS_PER_RUN:
        q = (
            sb.table(table)
            .select(",".join(columns))
            .lt(ts_col, before)
            .order("id")
            .limit(PAGE)
        )
        # Keyset pagination: stable and fast even while rows are being added.
        if rows:
            q = q.gt("id", rows[-1]["id"])
        page = q.execute().data or []
        rows.extend(page)
        if len(page) < PAGE:
            break
    return rows[:MAX_ROWS_PER_RUN]


def export(sb, out: Path, now: datetime) -> dict:
    c = cutoffs(now)
    # Unique per run, so a second run on the same day never overwrites the
    # first run's files (whose rows are already deleted).
    stamp = Path(now.strftime("%Y")) / now.strftime("%m-%d_%H%M%S")
    manifest: dict = {"created_at": now.isoformat(), **c, "files": [],
                      "history_ids": [], "offer_ids": []}

    history = _fetch_older(sb, "price_history", HISTORY_COLUMNS, "observed_at", c["history_before"])
    if history:
        f = out / "data" / stamp / "price_history.csv.gz"
        write_csv_gz(f, HISTORY_COLUMNS, history)
        manifest["files"].append(str(f.relative_to(out)))
        manifest["history_ids"] = [r["id"] for r in history]

    # Offers are only exported once their whole history is gone from the DB
    # (i.e. the history backlog is fully worked off) — otherwise the cascade
    # would delete history rows we haven't archived yet.
    if len(history) < MAX_ROWS_PER_RUN:
        cols = _existing_columns(sb, "offers", OFFER_COLUMNS)
        offers = _fetch_older(sb, "offers", cols, "last_seen_at", c["offers_before"])
        if offers:
            f = out / "data" / stamp / "offers.csv.gz"
            write_csv_gz(f, cols, offers)
            manifest["files"].append(str(f.relative_to(out)))
            manifest["offer_ids"] = [r["id"] for r in offers]

    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest))
    logger.info("exported %d price_history rows, %d offers",
                len(manifest["history_ids"]), len(manifest["offer_ids"]))
    return manifest


def verify_archive(out: Path, manifest: dict) -> None:
    """Refuse to delete anything the archive files don't actually contain."""
    archived: dict[str, set] = {"price_history": set(), "offers": set()}
    for rel in manifest["files"]:
        table = Path(rel).name.split(".")[0]
        archived[table] |= {str(r["id"]) for r in read_csv_gz(out / rel)}
    for key, table in (("history_ids", "price_history"), ("offer_ids", "offers")):
        missing = {str(i) for i in manifest[key]} - archived[table]
        if missing:
            raise RuntimeError(f"{len(missing)} {table} ids not in archive — not pruning")


def prune(sb, out: Path, manifest: dict) -> dict:
    verify_archive(out, manifest)
    deleted = {"price_history": 0, "offers": 0}
    for ids in chunks(manifest["history_ids"], DELETE_CHUNK):
        sb.table("price_history").delete().in_("id", ids) \
            .lt("observed_at", manifest["history_before"]).execute()
        deleted["price_history"] += len(ids)
    for ids in chunks(manifest["offer_ids"], DELETE_CHUNK):
        # Re-check the age: an offer that came back since the export stays.
        sb.table("offers").delete().in_("id", ids) \
            .lt("last_seen_at", manifest["offers_before"]).execute()
        deleted["offers"] += len(ids)
    logger.info("pruned %(price_history)d price_history rows, %(offers)d offers", deleted)

    try:
        res = sb.rpc("deactivate_stale_offers", {"max_age_days": EMBEDDING_DAYS}).execute()
        logger.info("deactivate_stale_offers: %s", res.data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("deactivate_stale_offers failed: %s", exc)
    return deleted


def report(sb) -> None:
    """Log table sizes (needs migration 012) so growth shows up in the Action log."""
    try:
        rows = sb.rpc("storage_report", {}).execute().data or []
    except Exception as exc:  # noqa: BLE001
        logger.info("storage_report unavailable (%s) — apply migration 012", exc)
        return
    for r in rows:
        logger.info("size %-28s %8.1f MB  (%s rows est.)",
                    r["relation"], r["total_bytes"] / 1e6, r["row_estimate"])


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--out", type=Path, default=Path("archive_out"))
    p = sub.add_parser("prune")
    p.add_argument("--manifest", type=Path, default=Path("archive_out/manifest.json"))
    sub.add_parser("report")
    args = ap.parse_args()

    from providers.supabase_client import get_supabase
    sb = get_supabase()
    if args.cmd == "export":
        export(sb, args.out, datetime.now(timezone.utc))
    elif args.cmd == "prune":
        manifest = json.loads(args.manifest.read_text())
        prune(sb, args.manifest.parent, manifest)
        report(sb)
    else:
        report(sb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
