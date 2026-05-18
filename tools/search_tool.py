"""LangChain tool wrapping the Supabase search_offers RPC."""

import logging
from typing import Optional

from langchain_core.tools import tool

from providers.embeddings import embed_text
from providers.supabase_client import get_supabase
from scraper.utils import berlin_today

logger = logging.getLogger(__name__)


def semantic_search(
    query: str,
    max_price: Optional[float] = None,
    category: Optional[str] = None,
    limit: int = 10,
    similarity_cutoff: float = 0.55,
) -> list[dict]:
    """
    Embed *query* and call the Supabase search_offers RPC.
    Returns a list of offer dicts ordered by cosine similarity.
    """
    embedding = embed_text(query)

    try:
        result = get_supabase().rpc(
            "search_offers",
            {
                "query_embedding":   embedding,
                "similarity_cutoff": similarity_cutoff,
                "max_price_filter":  max_price,
                "category_filter":   category,
                "result_limit":      limit,
            },
        ).execute()
        return result.data or []
    except Exception as exc:
        logger.error("search_offers RPC failed: %s", exc)
        return []


def latest_offers(limit: int = 10, only_current: bool = False) -> list[dict]:
    """Return latest active offers with optional 'currently valid' filtering."""
    try:
        query = (
            get_supabase()
            .table("offers")
            .select(
                "id,title,price,original_price,discount_percent,store,category,url,image_url,"
                "validity_text,valid_from,valid_to,is_upcoming,scraped_at,"
                "offer_analyses(deal_verdict,quality_score,tags,key_features)"
            )
            .eq("is_active", True)
        )

        if only_current:
            today = berlin_today().isoformat()
            query = query.or_(
                f"valid_from.is.null,and(valid_from.lte.{today},valid_to.is.null),"
                f"and(valid_from.lte.{today},valid_to.gte.{today}),"
                f"and(valid_from.is.null,valid_to.gte.{today})"
            )

        result = (
            query
            .order("is_upcoming", desc=False)
            .order("valid_from", desc=False, nullsfirst=False)
            .order("discount_percent", desc=True, nullslast=True)
            .order("scraped_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
        normalized: list[dict] = []
        for row in rows:
            analysis_rows = row.pop("offer_analyses", None) or []
            analysis = analysis_rows[0] if analysis_rows else {}
            normalized.append({**row, **analysis})
        return normalized
    except Exception as exc:
        logger.error("latest_offers query failed: %s", exc)
        return []


def search_brochure_pages(
    query: str,
    limit: int = 8,
    stores: Optional[list[str]] = None,
) -> list[dict]:
    """Search persisted brochure pages with simple text matching."""
    try:
        sb_query = get_supabase().table("brochure_pages").select(
            "id,external_id,store,category,title,brochure_title,viewer_url,image_url,"
            "page_number,validity_text,valid_from,valid_to,is_upcoming,scraped_at"
        )

        lowered = query.lower()
        terms = [term for term in lowered.replace(",", " ").split() if len(term) >= 3]
        text_terms = [term for term in terms if term not in {"prospekt", "katalog", "kataloge", "seite"}]

        if stores:
            store_clauses = ",".join(f"store.ilike.%{store}%" for store in stores)
            sb_query = sb_query.or_(store_clauses)

        if text_terms:
            clauses: list[str] = []
            for term in text_terms:
                clauses.extend(
                    [
                        f"title.ilike.%{term}%",
                        f"brochure_title.ilike.%{term}%",
                        f"store.ilike.%{term}%",
                    ]
                )
            text_clauses = ",".join(clauses)
            sb_query = sb_query.or_(text_clauses)

        result = (
            sb_query
            .order("scraped_at", desc=True)
            .order("page_number", desc=False)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
        return [{**row, "result_type": "brochure_page", "url": row.get("viewer_url")} for row in rows]
    except Exception as exc:
        logger.error("search_brochure_pages failed: %s", exc)
        return []


def latest_brochure_pages(limit: int = 8, stores: Optional[list[str]] = None) -> list[dict]:
    """Return latest persisted brochure pages, optionally filtered by store."""
    try:
        query = get_supabase().table("brochure_pages").select(
            "id,external_id,store,category,title,brochure_title,viewer_url,image_url,"
            "page_number,validity_text,valid_from,valid_to,is_upcoming,scraped_at"
        )

        if stores:
            query = query.or_(",".join(f"store.ilike.%{store}%" for store in stores))

        result = (
            query
            .order("scraped_at", desc=True)
            .order("page_number", desc=False)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
        return [{**row, "result_type": "brochure_page", "url": row.get("viewer_url")} for row in rows]
    except Exception as exc:
        logger.error("latest_brochure_pages failed: %s", exc)
        return []


@tool
def search_offers_tool(query: str, max_price: Optional[float] = None) -> str:
    """
    Sucht semantisch nach Angeboten in der Datenbank.
    Gibt eine formatierte Liste der relevantesten Angebote zurück.

    Args:
        query: Suchanfrage auf Deutsch (z.B. 'Laptop für Studenten')
        max_price: Maximaler Preis in Euro (optional)
    """
    results = semantic_search(query, max_price=max_price, limit=10)
    if not results:
        return "Keine Angebote gefunden."

    lines = []
    for i, r in enumerate(results, 1):
        price_str = f"€{r['price']:.2f}" if r.get("price") else "Preis unbekannt"
        disc_str = f" (-{r['discount_percent']:.0f}%)" if r.get("discount_percent") else ""
        lines.append(
            f"{i}. {r['title']} — {price_str}{disc_str} | {r.get('store','?')} | "
            f"{r.get('deal_verdict','?')} | {r.get('url','')}"
        )
    return "\n".join(lines)
