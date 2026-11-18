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
  offers         seen in the last OFFER_DAYS days. kaufDA issues new offer ids
                 every week, so old rows pile up fast (193k rows / 587 MB in
                 Nov 2026 while only ~3k were current). The dashboard only
                 shows offers seen in the last 8 days.
  price_history  last HISTORY_DAYS days for offers that are kept (deal score
                 uses 90). A deleted offer's history is archived WITH it —
                 deleting an offer cascades to its history.
  embeddings     cleared for offers unseen for EMBEDDING_DAYS (existing RPC)

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

HISTORY_DAYS = 100
OFFER_DAYS = 30
EMBEDDING_DAYS = 14

PAGE = 1000
# Bound each run so a large first backlog is worked off over several runs
# instead of one run that hits the Actions timeout.
MAX_OFFERS_PER_RUN = 40_000
MAX_HISTORY_PER_RUN = 150_000
ID_CHUNK = 200          # uuids per request (URL length)
HISTORY_ID_CHUNK = 500  # bigint ids per request

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


def _fetch_older(sb, table: str, columns: list[str], ts_col: str, before: str, cap: int) -> list[dict]:
    """Rows with ts_col < before, ordered by id, at most `cap`."""
    rows: list[dict] = []
    while len(rows) < cap:
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
    return rows[:cap]


def _history_of(sb, offer_ids: list[str]) -> list[dict]:
    """ALL price_history rows of these offers (any age)."""
    rows: list[dict] = []
    for ids in chunks(offer_ids, ID_CHUNK):
        last = None
        while True:
            q = (
                sb.table("price_history")
                .select(",".join(HISTORY_COLUMNS))
                .in_("offer_id", ids)
                .order("id")
                .limit(PAGE)
            )
            if last is not None:
                q = q.gt("id", last)
            page = q.execute().data or []
            rows.extend(page)
            if len(page) < PAGE:
                break
            last = page[-1]["id"]
    return rows


def export(sb, out: Path, now: datetime) -> dict:
    c = cutoffs(now)
    # Unique per run, so a second run on the same day never overwrites the
    # first run's files (whose rows are already deleted).
    stamp = Path(now.strftime("%Y")) / now.strftime("%m-%d_%H%M%S")
    manifest: dict = {"created_at": now.isoformat(), **c, "files": [],
                      "history_ids": [], "offer_ids": []}

    # 1. Long-unseen offers + every history row they own (the delete cascades).
    cols = _existing_columns(sb, "offers", OFFER_COLUMNS)
    offers = _fetch_older(sb, "offers", cols, "last_seen_at", c["offers_before"], MAX_OFFERS_PER_RUN)
    history = _history_of(sb, [o["id"] for o in offers])

    # 2. Old history of offers that stay.
    budget = MAX_HISTORY_PER_RUN - len(history)
    if budget > 0:
        have = {r["id"] for r in history}
        older = _fetch_older(sb, "price_history", HISTORY_COLUMNS, "observed_at",
                             c["history_before"], budget)
        history += [r for r in older if r["id"] not in have]

    if offers:
        f = out / "data" / stamp / "offers.csv.gz"
        write_csv_gz(f, cols, offers)
        manifest["files"].append(str(f.relative_to(out)))
        manifest["offer_ids"] = [o["id"] for o in offers]
    if history:
        f = out / "data" / stamp / "price_history.csv.gz"
        write_csv_gz(f, HISTORY_COLUMNS, history)
        manifest["files"].append(str(f.relative_to(out)))
        manifest["history_ids"] = [r["id"] for r in history]

    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest))
    logger.info("exported %d offers, %d price_history rows",
                len(manifest["offer_ids"]), len(manifest["history_ids"]))
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
    # History first, by id: these rows are in the archive whatever their age.
    for ids in chunks(manifest["history_ids"], HISTORY_ID_CHUNK):
        sb.table("price_history").delete().in_("id", ids).execute()
        deleted["price_history"] += len(ids)
    for ids in chunks(manifest["offer_ids"], ID_CHUNK):
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
