"""Query node — semantic search + RAG to answer user questions about offers."""

import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from providers.llm import get_llm
from tools.search_tool import semantic_search
from workflow.state import AgentState

logger = logging.getLogger(__name__)

RAG_SYSTEM = """\
Du bist AngebotsBot, ein hilfreicher Angebots-Assistent auf Deutsch.
Du bekommst eine Nutzerfrage und eine Liste relevanter Angebote aus einer Datenbank.
Beantworte die Frage natürlich und empfiehl die besten Angebote.
Formatiere Preise als "€X,XX". Erwähne Bewertungen (Sehr gut/Gut/etc.) und Rabatte.
Wenn keine passenden Angebote gefunden wurden, sag das ehrlich."""


def _extract_price_filter(query: str) -> Optional[float]:
    """Extract a 'unter X Euro' price filter from the query string."""
    match = re.search(r'unter\s+([\d,.]+)\s*(?:euro|€|eur)?', query, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def query_node(state: AgentState) -> dict:
    """Search the DB for relevant offers and generate a RAG response."""
    query = state.get("user_query", "")
    if not query:
        return {"query_results": [], "final_response": "Bitte stelle eine konkrete Frage."}

    max_price = _extract_price_filter(query)

    results = semantic_search(query, max_price=max_price, limit=8, similarity_cutoff=0.5)

    if not results:
        return {
            "query_results": [],
            "final_response": (
                "Ich habe leider keine passenden Angebote in der Datenbank gefunden. "
                "Versuche es mit anderen Suchbegriffen oder lade zuerst neue Angebote."
            ),
        }

    # Build context block for the LLM
    offer_lines = []
    for i, r in enumerate(results, 1):
        price_str = f"€{r['price']:.2f}" if r.get("price") else "?"
        orig_str  = f" (war €{r['original_price']:.2f})" if r.get("original_price") else ""
        disc_str  = f" -{r['discount_percent']:.0f}%" if r.get("discount_percent") else ""
        feats = ", ".join((r.get("key_features") or [])[:3])
        offer_lines.append(
            f"{i}. {r['title']}\n"
            f"   Preis: {price_str}{orig_str}{disc_str} | Shop: {r.get('store','?')}\n"
            f"   Bewertung: {r.get('deal_verdict','?')} | Features: {feats or '–'}\n"
            f"   URL: {r.get('url','')}"
        )

    context = "\n\n".join(offer_lines)
    user_message = f"Nutzerfrage: {query}\n\nGefundene Angebote:\n{context}"

    try:
        llm = get_llm(temperature=0.3)
        response = llm.invoke([
            SystemMessage(content=RAG_SYSTEM),
            HumanMessage(content=user_message),
        ])
        answer = response.content.strip()
    except Exception as exc:
        logger.error("Query node LLM call failed: %s", exc)
        answer = f"Ich habe {len(results)} passende Angebote gefunden. Bitte schau dir die Liste an."

    return {"query_results": results, "final_response": answer}
