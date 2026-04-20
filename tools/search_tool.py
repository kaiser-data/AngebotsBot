"""LangChain tool wrapping the Supabase search_offers RPC."""

import logging
from typing import Optional

from langchain_core.tools import tool

from providers.embeddings import embed_text
from providers.supabase_client import get_supabase

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
