"""
Store node — batch-upserts scraped offers into Supabase.

Uses the same chunked upsert path as `scripts/run_scrape.py` (offers +
price_history). Optional vision analyses are written in one batch afterwards.

Embeddings are NOT computed in Python. The DB trigger `offers_embed_on_insert`
calls the generate-embedding Edge Function for new rows.
"""

import logging

import config
from providers.supabase_client import get_supabase
from scripts.run_scrape import upsert_offers
from workflow.state import AgentState, AnalyzedOffer

logger = logging.getLogger(__name__)


def store_node(state: AgentState) -> dict:
    """Batch-upsert scraped offers; optionally attach vision analyses."""
    offers = state.get("scraped_offers", [])
    analyses = state.get("analyzed_offers", [])
    if not offers:
        return {"offers_stored": [], "db_errors": []}

    db_errors: list[str] = []
    try:
        returned = upsert_offers(offers)
    except Exception as exc:
        msg = f"Batch upsert failed: {exc}"
        logger.error(msg)
        return {"offers_stored": [], "db_errors": [msg]}

    stored_ids = [r["id"] for r in returned if r.get("id")]
    if not stored_ids and offers:
        db_errors.append("Upsert returned no rows")

    analysis_map: dict[str, AnalyzedOffer] = {a["external_id"]: a for a in analyses}
    if analysis_map and returned:
        analysis_rows = []
        for row in returned:
            analysis = analysis_map.get(row.get("external_id"))
            if not analysis:
                continue
            analysis_rows.append({
                "offer_id":         row["id"],
                "product_name":     analysis.get("product_name"),
                "brand":            analysis.get("brand"),
                "condition":        analysis.get("condition"),
                "key_features":     analysis.get("key_features"),
                "quality_score":    analysis.get("quality_score"),
                "deal_verdict":     analysis.get("deal_verdict"),
                "tags":             analysis.get("tags"),
                "raw_llm_response": analysis.get("raw_llm_response"),
                "model_used":       config.VISION_MODEL,
            })
        if analysis_rows:
            try:
                get_supabase().table("offer_analyses").upsert(
                    analysis_rows,
                    on_conflict="offer_id",
                ).execute()
            except Exception as exc:
                msg = f"offer_analyses batch upsert failed: {exc}"
                logger.error(msg)
                db_errors.append(msg)

    logger.info("Store node: stored %d offers, %d errors", len(stored_ids), len(db_errors))

    try:
        from providers.embeddings import drain_embedding_queue
        drain_embedding_queue(limit=min(200, max(len(stored_ids), 1) * 2))
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding drain skipped: %s", exc)

    return {"offers_stored": stored_ids, "db_errors": db_errors}
