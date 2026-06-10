"""
LLM categorization worker.

Reads offers that have no row in `llm_categories` for the current MODEL_VERSION,
batches them, sends to Gemini, and writes the structured result back. Versioned
so re-running with a bumped MODEL_VERSION re-classifies everything without
losing prior results.

Usage:
    python -m scripts.categorize_offers                  # up to 200 uncategorized
    python -m scripts.categorize_offers --limit 1000
    python -m scripts.categorize_offers --all
    python -m scripts.categorize_offers --force          # ignore existing rows
    python -m scripts.categorize_offers --model-version v2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import date
from typing import Iterable

from langchain_core.messages import HumanMessage, SystemMessage

import config
from providers.llm import get_llm
from providers.supabase_client import get_supabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("categorize")

# Bump this string to force re-classification of everything.
# v2: introduced canonical subcategory taxonomy (mirror of dashboard/src/lib/taxonomy.ts).
MODEL_VERSION = "v2"
BATCH_SIZE = 25

# Max concurrent LLM batch calls. Batches are independent, so we fan them out
# with a semaphore (same pattern as agents/vision_node.py) instead of running
# serially — this is what keeps the daily GitHub Actions run under its time
# budget even with a backlog. Override with CATEGORIZE_CONCURRENCY.
CONCURRENCY = int(os.getenv("CATEGORIZE_CONCURRENCY", "5"))

# ── Canonical taxonomy ──
# IMPORTANT: keep in sync with dashboard/src/lib/taxonomy.ts.
# If you change anything here, mirror it there and bump MODEL_VERSION.
TAXONOMY: list[str] = [
    "Lebensmittel",
    "Getränke",
    "Drogerie & Kosmetik",
    "Haushalt & Reinigung",
    "Baby & Kind",
    "Tier",
    "Garten & Heimwerken",
    "Elektronik & Multimedia",
    "Mode, Sport & Freizeit",
    "Sonstiges",
]

SUBCATEGORIES: dict[str, list[str]] = {
    "Lebensmittel": [
        "Obst & Gemüse", "Fleisch & Wurst", "Fisch", "Milchprodukte & Käse",
        "Brot & Backwaren", "Süßwaren & Snacks", "Tiefkühl", "Grundnahrung & Konserven",
    ],
    "Getränke": [
        "Wasser & Säfte", "Bier", "Wein & Sekt", "Spirituosen", "Kaffee & Tee",
    ],
    "Drogerie & Kosmetik": [
        "Körperpflege", "Kosmetik & Make-up", "Gesundheit & Apotheke", "Parfum & Düfte",
    ],
    "Haushalt & Reinigung": [
        "Waschmittel", "Reinigung", "Küchenbedarf", "Aufbewahrung",
    ],
    "Baby & Kind": [
        "Windeln & Pflege", "Baby-Nahrung", "Spielzeug",
    ],
    "Tier": [
        "Hund", "Katze", "Sonstige Tiere",
    ],
    "Garten & Heimwerken": [
        "Pflanzen & Garten", "Gartenwerkzeug", "Werkzeug & Heimwerken",
        "Farbe & Bauchemie", "Gartenmöbel",
    ],
    "Elektronik & Multimedia": [
        "Smartphone & Tablet", "Computer & Drucker", "TV & Audio",
        "Haushaltsgeräte", "Sonstige Elektronik",
    ],
    "Mode, Sport & Freizeit": [
        "Kleidung & Schuhe", "Sport & Fitness", "Outdoor", "Spielzeug & Hobby",
    ],
    "Sonstiges": [
        "Auto & Mobilität", "Büro & Schreibwaren", "Sonstige",
    ],
}

# Few-shot examples teach the model:
#   - kaufDA's `category` column is a noisy keyword hint, NOT ground truth
#   - brand/product disambiguation (Apple Inc. ≠ Apfel, "Ariel" = detergent, "Funny-Frisch" = chips)
#   - normalized subcategory vocabulary (short, capitalised, German)
FEW_SHOT_EXAMPLES = [
    {"title": "Ariel Universal Waschpulver 80 WL",
     "store": "REWE", "kaufda_category": "Ariel",
     "expected": {"category": "Drogerie & Kosmetik", "subcategory": "Waschmittel",
                  "confidence": 0.98, "reasoning": "Markenname Ariel = Waschmittel"}},
    {"title": "Apple iPhone 15 128GB",
     "store": "Saturn", "kaufda_category": "Apple",
     "expected": {"category": "Elektronik & Multimedia", "subcategory": "Smartphone",
                  "confidence": 0.99, "reasoning": "Apple-Marke, nicht Frucht"}},
    {"title": "Funny-Frisch Chipsfrisch ungarisch 175g",
     "store": "Edeka", "kaufda_category": "Funny-Frisch",
     "expected": {"category": "Lebensmittel", "subcategory": "Chips",
                  "confidence": 0.97, "reasoning": "Chips-Marke"}},
    {"title": "Apfel Elstar lose, 1 kg",
     "store": "REWE", "kaufda_category": "Apfel",
     "expected": {"category": "Lebensmittel", "subcategory": "Apfel",
                  "confidence": 0.99, "reasoning": "Frisches Obst"}},
    {"title": "Felix Knabberminis Huhn 200g",
     "store": "Fressnapf", "kaufda_category": "Felix",
     "expected": {"category": "Tier", "subcategory": "Katzenfutter",
                  "confidence": 0.98, "reasoning": "Felix ist Katzenfutter-Marke"}},
    {"title": "Aperol Aperitivo 11% 0,7l",
     "store": "Kaufland", "kaufda_category": "Aperol",
     "expected": {"category": "Getränke", "subcategory": "Aperitif",
                  "confidence": 0.99, "reasoning": "Alkohol-Aperitif"}},
    {"title": "Akku-Rasenmäher Bosch 36V",
     "store": "OBI", "kaufda_category": "Akku-Rasenmaeher",
     "expected": {"category": "Garten & Heimwerken", "subcategory": "Rasenmäher",
                  "confidence": 0.98, "reasoning": "Gartengerät"}},
    {"title": "Pampers Premium Protection Größe 4",
     "store": "dm", "kaufda_category": "Babywindeln",
     "expected": {"category": "Baby & Kind", "subcategory": "Windeln",
                  "confidence": 0.99, "reasoning": "Babywindeln"}},
]

SUBCATEGORY_GUIDANCE = "Erlaubte Unterkategorien pro Kategorie (KEINE anderen erfinden):\n" + "\n".join(
    f"- {bucket}: " + ", ".join(f'"{s}"' for s in subs)
    for bucket, subs in SUBCATEGORIES.items()
)

# Pre-rendered as a top-level string so the SYSTEM_PROMPT f-string below
# doesn't need any escapes inside its expressions (Python 3.11 forbids
# backslashes inside f-string expression parts; PEP 701 only lifts that
# restriction in 3.12+).
_FEW_SHOT_BLOCK = "\n".join(
    f"  Input:  {{title='{ex['title']}', store='{ex['store']}', kaufda_category='{ex['kaufda_category']}'}}\n"
    f"  Output: {ex['expected']}"
    for ex in FEW_SHOT_EXAMPLES
)

SYSTEM_PROMPT = f"""Du bist ein Klassifikations-Service für deutsche Supermarkt- und Drogerie-Angebote.

Für jedes Angebot wählst du GENAU EINE Kategorie aus dieser festen Taxonomie:
{chr(10).join(f"- {c}" for c in TAXONOMY)}

Außerdem wählst du GENAU EINE `subcategory` aus der unten erlaubten Liste — KEINE anderen Werte!
Eine confidence zwischen 0 und 1.

WICHTIG zu den Eingabe-Feldern:
- `title` ist die wichtigste Quelle. Lies ihn vollständig.
- `kaufda_category` ist nur ein NOISIGER Stichwort-Hinweis (oft nur der Markenname oder ein
  Sub-String). Vertraue ihm NICHT blind, sondern nutze ihn nur als zusätzlichen Hint.
- `store` hilft bei Mehrdeutigkeit (Saturn → eher Elektronik; Fressnapf → Tier; dm → Drogerie).

Disambiguierung wichtiger Verwechslungen:
- "Apple" als Marke → Elektronik; "Apfel" als Frucht → Lebensmittel.
- "Ariel" → Waschmittel (Drogerie & Kosmetik), kein Lebensmittel.
- "Felix" → Katzenfutter (Tier), nicht Lebensmittel.
- "Express" / "App" → meist Sonstiges/Werbung, nicht eigene Kategorie.
- Bei Bio-/Marken-Lebensmittel wie "Alnatura", "Alpro" → Lebensmittel.
- "Akku-X" → Elektronik wenn Standalone-Akku/Gerät, Garten & Heimwerken wenn Werkzeug
  (Akku-Rasenmäher, Akku-Heckenschere, Akku-Bohrschrauber).

{SUBCATEGORY_GUIDANCE}

Beispiele (input → expected output):
{_FEW_SHOT_BLOCK}

Antworte ausschließlich mit gültigem JSON in genau diesem Format:
{{"results": [
  {{"external_id": "...", "category": "<eine aus der Taxonomie>", "subcategory": "...", "confidence": 0.0-1.0, "reasoning": "kurzer Hinweis"}}
]}}

Regeln:
- `category` MUSS exakt einer der 10 Taxonomie-Strings sein.
- `subcategory` MUSS exakt einer der erlaubten Subcategory-Strings für die gewählte category sein.
  Erfinde KEINE neuen Subcategories. Wenn nichts passt, nimm die generischste verfügbare
  (z. B. "Sonstige Elektronik", "Grundnahrung & Konserven", "Sonstige").
- Wenn unsicher bei der Top-Level-Kategorie: niedrige confidence + Kategorie "Sonstiges" + "Sonstige".
- Bewahre die Reihenfolge der Eingabe-Items im `results`-Array.
"""


def fetch_uncategorized(limit: int | None, force: bool, model_version: str) -> list[dict]:
    """Return offers needing classification for this model_version.

    The diff (which active offers lack a row for this model_version) is computed
    in Postgres via the fetch_uncategorized_offers RPC (migration 008) rather than
    paging every offer + every category into Python. Results come back already
    limited and newest-first.
    """
    sb = get_supabase()
    res = sb.rpc(
        "fetch_uncategorized_offers",
        {
            "p_model_version": model_version,
            "p_limit": limit,
            "p_force": force,
        },
    ).execute()
    pending = res.data or []
    logger.info(
        "%d offers pending classification (model_version=%s, force=%s, limit=%s)",
        len(pending), model_version, force, limit,
    )
    return pending


def chunks(items: list[dict], n: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def extract_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in ```json fences or add prose — extract the object."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span (prose before/after the JSON).
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _build_user_message(batch: list[dict], with_vision: bool) -> HumanMessage:
    """Build the HumanMessage for one batch (text-only or multimodal).

    When with_vision=True, each offer's image_url is included as an image_url
    content part alongside the text payload. Gemini 2.5 Flash is multimodal and
    will use the product photo to disambiguate ambiguous titles. ~2-3× more
    expensive per call.
    """
    payload = [
        {
            "external_id": o["external_id"],
            "title": o["title"],
            "store": o.get("store"),
            "kaufda_category": o.get("category"),
        }
        for o in batch
    ]
    text_part = "Klassifiziere diese Angebote:\n" + json.dumps(payload, ensure_ascii=False, indent=2)

    if not with_vision:
        return HumanMessage(content=text_part)

    # Multipart content: text + one image_url per offer with an image.
    # We label each image so the model can correlate it to the right item.
    content_parts: list[dict] = [{"type": "text", "text": text_part}]
    for o in batch:
        url = (o.get("image_url") or "").strip()
        if not url:
            continue
        content_parts.append({
            "type": "text",
            "text": f"\nProduktfoto für external_id={o['external_id']}:",
        })
        content_parts.append({"type": "image_url", "image_url": {"url": url}})
    return HumanMessage(content=content_parts)


def _parse_results(content: str, batch: list[dict]) -> list[dict]:
    """Parse + validate one LLM response into upsert-ready llm_categories rows."""
    try:
        parsed = extract_json(content)
        results = parsed.get("results", [])
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse LLM response: %s\n---\n%s", exc, content[:500])
        return []

    # Index batch by external_id for offer_id lookup.
    by_ext = {o["external_id"]: o for o in batch}
    rows: list[dict] = []
    coerced = 0
    for r in results:
        ext = r.get("external_id")
        cat = r.get("category")
        if not ext or not cat or ext not in by_ext or cat not in TAXONOMY:
            logger.warning("Skipping invalid result: %s", r)
            continue

        # Enforce the canonical subcategory taxonomy. If the model returns a
        # non-canonical subcategory, coerce it to the safest generic for the bucket.
        raw_sub = (r.get("subcategory") or "").strip()
        allowed = SUBCATEGORIES.get(cat, [])
        if raw_sub in allowed:
            sub = raw_sub
        else:
            # Generic fallbacks per bucket.
            fallback = {
                "Lebensmittel": "Grundnahrung & Konserven",
                "Getränke": "Wasser & Säfte",
                "Drogerie & Kosmetik": "Körperpflege",
                "Haushalt & Reinigung": "Reinigung",
                "Baby & Kind": "Spielzeug",
                "Tier": "Sonstige Tiere",
                "Garten & Heimwerken": "Werkzeug & Heimwerken",
                "Elektronik & Multimedia": "Sonstige Elektronik",
                "Mode, Sport & Freizeit": "Kleidung & Schuhe",
                "Sonstiges": "Sonstige",
            }.get(cat, "Sonstige")
            sub = fallback
            coerced += 1
            logger.debug("Coerced subcategory %r → %r for bucket %r", raw_sub, sub, cat)

        rows.append({
            "external_id":   ext,
            "offer_id":      by_ext[ext]["id"],
            "category":      cat,
            "subcategory":   sub,
            "confidence":    float(r.get("confidence") or 0.5),
            "model":         config.TEXT_MODEL,
            "model_version": MODEL_VERSION,
            "reasoning":     (r.get("reasoning") or "")[:500] or None,
        })
    if coerced:
        logger.info("  ↳ coerced %d non-canonical subcategories", coerced)
    return rows


def classify_batch(batch: list[dict], with_vision: bool = False) -> list[dict]:
    """Send one batch to the LLM synchronously and return parsed rows."""
    llm = get_llm(temperature=0.0)
    user_msg = _build_user_message(batch, with_vision)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), user_msg])
    content = response.content if isinstance(response.content, str) else str(response.content)
    return _parse_results(content, batch)


async def _classify_batch_async(
    batch: list[dict],
    with_vision: bool,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Async single-batch classify, gated by a semaphore. Never raises —
    a failed batch logs and yields no rows so the rest of the run continues."""
    async with semaphore:
        llm = get_llm(temperature=0.0)
        user_msg = _build_user_message(batch, with_vision)
        try:
            response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), user_msg])
        except Exception as exc:  # noqa: BLE001
            logger.error("Batch failed (%d offers): %s", len(batch), exc)
            return []
        content = response.content if isinstance(response.content, str) else str(response.content)
        return _parse_results(content, batch)


async def categorize_pending_async(
    pending: list[dict],
    with_vision: bool = False,
    concurrency: int = CONCURRENCY,
) -> int:
    """Classify all pending offers with up to `concurrency` batches in flight.

    LLM calls (the slow, I/O-bound part) are fanned out concurrently; the parsed
    rows are then upserted sequentially via the sync Supabase client after the
    gather, so we never block the event loop on DB writes.
    """
    if not pending:
        return 0

    semaphore = asyncio.Semaphore(concurrency)
    batches = list(chunks(pending, BATCH_SIZE))
    logger.info(
        "Categorizing %d offers in %d batches (concurrency=%d)%s",
        len(pending), len(batches), concurrency, " [vision]" if with_vision else "",
    )

    tasks = [_classify_batch_async(b, with_vision, semaphore) for b in batches]
    results = await asyncio.gather(*tasks)

    total_written = 0
    for rows in results:
        total_written += upsert_rows(rows)
    return total_written


def upsert_rows(rows: list[dict]) -> int:
    if not rows:
        return 0
    sb = get_supabase()
    sb.table("llm_categories").upsert(
        rows, on_conflict="external_id,model_version"
    ).execute()
    return len(rows)


def main() -> int:
    global MODEL_VERSION
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="Max offers to process (default 200)")
    ap.add_argument("--all", action="store_true", help="Process every uncategorized offer")
    ap.add_argument("--force", action="store_true", help="Re-classify even already-done offers")
    ap.add_argument("--weekly", action="store_true",
                    help="Use ISO-week-stamped model_version (e.g. v1-2026-W20). "
                         "Run weekly via cron to refresh classifications.")
    ap.add_argument("--vision", action="store_true",
                    help="Send product images to the LLM as well. Slower and ~2-3× more "
                         "expensive, but disambiguates brand/product collisions.")
    ap.add_argument("--model-version", default=None,
                    help=f"Override MODEL_VERSION (default {MODEL_VERSION!r}). "
                         "Ignored if --weekly is set.")
    args = ap.parse_args()

    if args.weekly:
        iso_year, iso_week, _ = date.today().isocalendar()
        MODEL_VERSION = f"v1-{iso_year}-W{iso_week:02d}"
        logger.info("Weekly mode: using model_version=%s", MODEL_VERSION)
    elif args.model_version:
        MODEL_VERSION = args.model_version

    limit = None if args.all else args.limit
    pending = fetch_uncategorized(limit=limit, force=args.force, model_version=MODEL_VERSION)
    if not pending:
        logger.info("Nothing to classify.")
        return 0

    start = time.time()
    total_written = asyncio.run(
        categorize_pending_async(pending, with_vision=args.vision)
    )
    elapsed = time.time() - start
    logger.info(
        "Done. %d / %d offers classified in %.1fs (model_version=%s)",
        total_written, len(pending), elapsed, MODEL_VERSION,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
