"""Query node — semantic search + RAG to answer user questions about offers."""

import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from providers.llm import get_llm
from scraper.utils import format_validity_window
from tools.search_tool import (
    latest_brochure_pages,
    latest_offers,
    search_brochure_pages,
    semantic_search,
)
from workflow.state import AgentState

logger = logging.getLogger(__name__)

RAG_SYSTEM = """\
Du bist AngebotsBot, ein hilfreicher Angebots-Assistent auf Deutsch.
Du bekommst eine Nutzerfrage und eine Liste relevanter Angebote aus einer Datenbank.
Beantworte die Frage natürlich und empfiehl die besten Angebote.
Formatiere Preise als "€X,XX". Erwähne Bewertungen (Sehr gut/Gut/etc.) und Rabatte.
Wenn vorhanden, erkläre klar die Gültigkeit des Angebots, z.B. "gültig bis 2026-05-18" oder "ab 2026-05-17".
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


def _is_generic_current_offers_query(query: str) -> bool:
    q = query.lower()
    patterns = [
        "was ist gerade im angebot",
        "was ist aktuell im angebot",
        "aktuelle angebote",
        "gerade im angebot",
        "heute im angebot",
        "welche angebote gibt es",
        "zeige aktuelle angebote",
    ]
    return any(pattern in q for pattern in patterns)


def _extract_store_filters(query: str) -> list[str]:
    q = query.lower()
    stores = []
    for store in ("lidl", "edeka", "aldi", "rewe", "penny", "netto"):
        if store in q:
            stores.append(store)
    return stores


def _is_brochure_query(query: str) -> bool:
    q = query.lower()
    return any(word in q for word in ("prospekt", "katalog", "kataloge", "seite", "flyer"))


def _format_source_list(results: list[dict]) -> str:
    lines = []
    for i, result in enumerate(results[:5], 1):
        label = result.get("brochure_title") or result.get("title") or "Quelle"
        url = result.get("url") or result.get("viewer_url") or ""
        if not url:
            continue
        lines.append(f"{i}. [{label}]({url})")
    return "\n".join(lines)


def query_node(state: AgentState) -> dict:
    """Search the DB for relevant offers and generate a RAG response."""
    query = state.get("user_query", "")
    if not query:
        return {"query_results": [], "final_response": "Bitte stelle eine konkrete Frage."}

    max_price = _extract_price_filter(query)
    if _is_brochure_query(query):
        store_filters = _extract_store_filters(query)
        results = search_brochure_pages(query, limit=8, stores=store_filters)
        if not results:
            results = latest_brochure_pages(limit=8, stores=store_filters)
        if not results:
            return {
                "query_results": [],
                "final_response": (
                    "Ich habe keine passenden Prospektseiten in der Datenbank gefunden. "
                    "Lade zuerst Kataloge über den Review-Flow oder versuche einen anderen Händler."
                ),
            }

        lines = []
        for i, r in enumerate(results, 1):
            validity = format_validity_window(r) or r.get("validity_text") or "Gültigkeit unbekannt"
            lines.append(
                f"{i}. **{r.get('store','?')}** — {r.get('brochure_title') or r.get('title') or '?'}\n"
                f"   Seite: {r.get('page_number','?')} | {validity}\n"
                f"   Link: {r.get('url') or r.get('viewer_url') or ''}"
            )

        answer = (
            "Ich habe passende Prospektseiten gefunden. "
            "Die Vorschaubilder werden unter der Antwort angezeigt.\n\n"
            + "\n\n".join(lines)
        )
        sources = _format_source_list(results)
        if sources:
            answer += f"\n\n**Quellen**\n{sources}"
        return {"query_results": results, "final_response": answer}

    if _is_generic_current_offers_query(query):
        results = latest_offers(limit=8, only_current=True)
        if not results:
            results = latest_offers(limit=8, only_current=False)
    else:
        results = semantic_search(query, max_price=max_price, limit=8, similarity_cutoff=0.5)
        if not results:
            results = latest_offers(limit=8, only_current=True) if "angebot" in query.lower() else []

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
        validity = format_validity_window(r) or "Gültigkeit unbekannt"
        offer_lines.append(
            f"{i}. {r['title']}\n"
            f"   Preis: {price_str}{orig_str}{disc_str} | Shop: {r.get('store','?')}\n"
            f"   Gültigkeit: {validity}\n"
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

    sources = _format_source_list(results)
    if sources:
        answer += f"\n\n**Quellen**\n{sources}"

    return {"query_results": results, "final_response": answer}
