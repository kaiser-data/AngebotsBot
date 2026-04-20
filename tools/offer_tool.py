"""Tools for fetching and listing individual offers."""

import logging
from typing import Optional

from providers.supabase_client import get_supabase
from tools.search_tool import semantic_search

logger = logging.getLogger(__name__)


def fetch_offer_by_id(offer_id: str) -> Optional[dict]:
    """Fetch a single offer with its analysis by UUID."""
    try:
        result = (
            get_supabase()
            .table("offers")
            .select("*, offer_analyses(*)")
            .eq("id", offer_id)
            .single()
            .execute()
        )
        return result.data
    except Exception as exc:
        logger.error("fetch_offer_by_id(%s) failed: %s", offer_id, exc)
        return None


def fetch_offers_by_keywords(keywords: str, limit: int = 10) -> list[dict]:
    """
    Find offers matching a keyword string via semantic search.
    Used by the comparison node to gather candidates.
    """
    return semantic_search(keywords, limit=limit, similarity_cutoff=0.45)


def list_categories() -> list[str]:
    """Return distinct categories present in the offers table."""
    try:
        result = (
            get_supabase()
            .table("offers")
            .select("category")
            .eq("is_active", True)
            .execute()
        )
        cats = {row["category"] for row in (result.data or []) if row.get("category")}
        return sorted(cats)
    except Exception as exc:
        logger.error("list_categories failed: %s", exc)
        return []
