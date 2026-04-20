"""
Store node — upserts scraped+analyzed offers into Supabase.

Embeddings werden NICHT in Python berechnet. Der Datenbank-Trigger
`offers_embed_on_insert` ruft automatisch die generate-embedding
Edge Function auf und schreibt das Embedding in die Zeile.
"""

import logging
from datetime import datetime, timezone

from providers.supabase_client import get_supabase
from workflow.state import AgentState, AnalyzedOffer

logger = logging.getLogger(__name__)


def store_node(state: AgentState) -> dict:
    """Upsert all scraped+analyzed offers into Supabase (no local embedding)."""
    offers   = state.get("scraped_offers", [])
    analyses = state.get("analyzed_offers", [])
    if not offers:
        return {"offers_stored": [], "db_errors": []}

    analysis_map: dict[str, AnalyzedOffer] = {a["external_id"]: a for a in analyses}
    sb = get_supabase()
    stored_ids: list[str] = []
    db_errors:  list[str] = []

    for offer in offers:
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Upsert ohne embedding — der DB-Trigger berechnet es async
            offer_row = {
                "external_id":      offer["external_id"],
                "title":            offer["title"],
                "url":              offer["url"],
                "image_url":        offer.get("image_url"),
                "price":            offer.get("price"),
                "original_price":   offer.get("original_price"),
                "discount_percent": offer.get("discount_percent"),
                "store":            offer.get("store"),
                "category":         offer.get("category"),
                "is_active":        True,
                "last_seen_at":     now,
                "scraped_at":       offer.get("scraped_at") or now,
                # embedding wird automatisch vom DB-Trigger gesetzt
            }

            result = (
                sb.table("offers")
                .upsert(offer_row, on_conflict="external_id")
                .execute()
            )
            rows = result.data or []
            if not rows:
                db_errors.append(f"Upsert returned no data for {offer['external_id']}")
                continue

            offer_id = rows[0]["id"]
            stored_ids.append(offer_id)

            # Analyse einfügen falls vorhanden
            analysis = analysis_map.get(offer["external_id"])
            if analysis:
                sb.table("offer_analyses").upsert(
                    {
                        "offer_id":         offer_id,
                        "product_name":     analysis.get("product_name"),
                        "brand":            analysis.get("brand"),
                        "condition":        analysis.get("condition"),
                        "key_features":     analysis.get("key_features"),
                        "quality_score":    analysis.get("quality_score"),
                        "deal_verdict":     analysis.get("deal_verdict"),
                        "tags":             analysis.get("tags"),
                        "raw_llm_response": analysis.get("raw_llm_response"),
                        "model_used":       "Qwen2.5-VL-32B-Instruct",
                    },
                    on_conflict="offer_id",
                ).execute()

        except Exception as exc:
            msg = f"DB error for {offer['external_id']}: {exc}"
            logger.error(msg)
            db_errors.append(msg)

    logger.info("Store node: stored %d offers, %d errors", len(stored_ids), len(db_errors))
    return {"offers_stored": stored_ids, "db_errors": db_errors}
