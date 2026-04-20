"""Comparison node — ranks and compares multiple offers side-by-side."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from providers.llm import get_llm
from tools.offer_tool import fetch_offers_by_keywords
from workflow.state import AgentState

logger = logging.getLogger(__name__)

COMPARISON_SYSTEM = """\
Du bist AngebotsBot. Du bekommst mehrere Angebote aus einer Datenbank.
Erstelle eine übersichtliche Vergleichstabelle in Markdown und schreibe danach ein kurzes Urteil.
Empfiehl das beste Preis-Leistungs-Verhältnis und begründe deine Empfehlung auf Deutsch."""


def _build_comparison_table(offers: list[dict]) -> str:
    """Build a Markdown table from a list of offer dicts."""
    if not offers:
        return ""

    header = "| # | Produkt | Preis | Rabatt | Shop | Bewertung |\n"
    sep    = "|---|---------|-------|--------|------|-----------|\n"
    rows   = []
    for i, o in enumerate(offers, 1):
        price = f"€{o['price']:.2f}" if o.get("price") else "?"
        disc  = f"-{o['discount_percent']:.0f}%" if o.get("discount_percent") else "–"
        rows.append(
            f"| {i} | [{o['title'][:40]}]({o.get('url','')}) "
            f"| {price} | {disc} | {o.get('store','?')} | {o.get('deal_verdict','?')} |"
        )
    return header + sep + "\n".join(rows)


def comparison_node(state: AgentState) -> dict:
    """Fetch relevant offers and generate a comparison table + verdict."""
    query = state.get("user_query", "")
    offers = fetch_offers_by_keywords(query, limit=6)

    if not offers:
        return {
            "query_results": [],
            "comparison_result": "Keine Angebote zum Vergleichen gefunden.",
            "final_response": "Keine Angebote zum Vergleichen gefunden.",
        }

    table = _build_comparison_table(offers)

    context = f"Nutzeranfrage: {query}\n\nAngebote zum Vergleich:\n{table}"

    try:
        llm = get_llm(temperature=0.3)
        response = llm.invoke([
            SystemMessage(content=COMPARISON_SYSTEM),
            HumanMessage(content=context),
        ])
        result = response.content.strip()
    except Exception as exc:
        logger.error("Comparison node LLM failed: %s", exc)
        result = table

    return {
        "query_results":    offers,
        "comparison_result": result,
        "final_response":   result,
    }
