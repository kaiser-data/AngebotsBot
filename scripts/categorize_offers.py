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
import json
import logging
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
{chr(10).join(
    f"  Input:  {{title='{ex['title']}', store='{ex['store']}', kaufda_category='{ex['kaufda_category']}'}}\n"
    f"  Output: {ex['expected']}"
    for ex in FEW_SHOT_EXAMPLES
)}

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
    """Return offers needing classification for this model_version."""
    sb = get_supabase()

    # Get every active offer's external_id + title (+ a couple of fields for context).
    # We page through in chunks because PostgREST caps at ~1000 rows per request.
    offers: list[dict] = []
    page = 0
    page_size = 1000
    while True:
        q = (
            sb.table("offers")
            .select("id, external_id, title, store, category, image_url")
            .eq("is_active", True)
            .range(page * page_size, (page + 1) * page_size - 1)
        )
        res = q.execute()
        rows = res.data or []
        offers.extend(rows)
        if len(rows) < page_size:
            break
        page += 1

    if force:
        already_done: set[str] = set()
    else:
        # Fetch external_ids that already have a row for this model_version.
        done_res = (
            sb.table("llm_categories")
            .select("external_id")
            .eq("model_version", model_version)
            .execute()
        )
        already_done = {r["external_id"] for r in (done_res.data or [])}

    pending = [o for o in offers if o["external_id"] not in already_done]
    if limit is not None:
        pending = pending[:limit]

    logger.info(
        "Offers: %d total, %d already classified, %d pending",
        len(offers),
        len(already_done),
        len(pending),
    )
    return pending


def chunks(items: list[dict], n: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def extract_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in ```json fences — strip them."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE)
    return json.loads(cleaned)


def classify_batch(batch: list[dict], with_vision: bool = False) -> list[dict]:
    """Send one batch to the LLM and return parsed results.

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

    if with_vision:
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
        user_msg: object = HumanMessage(content=content_parts)
    else:
        user_msg = HumanMessage(content=text_part)

    llm = get_llm(temperature=0.0)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), user_msg])
    content = response.content if isinstance(response.content, str) else str(response.content)

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


def upsert_rows(rows: list[dict]) -> int:
    if not rows:
        return 0
    sb = get_supabase()
    sb.table("llm_categories").upsert(
        rows, on_conflict="external_id,model_version"
    ).execute()
    return len(rows)


def main() -> int:
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

    global MODEL_VERSION
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

    total_written = 0
    total_batches = (len(pending) + BATCH_SIZE - 1) // BATCH_SIZE
    start = time.time()

    for i, batch in enumerate(chunks(pending, BATCH_SIZE), start=1):
        logger.info("Batch %d/%d: %d offers%s", i, total_batches, len(batch),
                    " [vision]" if args.vision else "")
        try:
            rows = classify_batch(batch, with_vision=args.vision)
            written = upsert_rows(rows)
            total_written += written
            logger.info("  → wrote %d rows", written)
        except Exception as exc:
            logger.error("Batch %d failed: %s", i, exc)
            continue

    elapsed = time.time() - start
    logger.info(
        "Done. %d / %d offers classified in %.1fs (model_version=%s)",
        total_written, len(pending), elapsed, MODEL_VERSION,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
