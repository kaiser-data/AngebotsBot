"""Response node — assembles the final Chainlit-ready Markdown response."""

import logging

from workflow.state import AgentState

logger = logging.getLogger(__name__)


def response_node(state: AgentState) -> dict:
    """
    Terminal node. If final_response is already set by a prior node, pass it through.
    Otherwise, build a summary from stored/error counters.
    """
    intent = state.get("intent", "unknown")

    # Most paths (query, compare, alert) already set final_response
    if state.get("final_response"):
        return {}  # nothing to change

    # ── Scrape path summary ───────────────────────────────────────────────────
    if intent == "scrape":
        stored     = len(state.get("offers_stored", []))
        scraped    = len(state.get("scraped_offers", []))
        analyzed   = len(state.get("analyzed_offers", []))
        s_errors   = state.get("scrape_errors", [])
        v_errors   = state.get("vision_errors", [])
        db_errors  = state.get("db_errors", [])

        if stored == 0 and scraped == 0:
            msg = "Keine neuen Angebote gefunden — die Datenbank ist bereits aktuell."
        else:
            msg = (
                f"**Scraping abgeschlossen!**\n\n"
                f"- Angebote gefunden: **{scraped}**\n"
                f"- In Datenbank gespeichert: **{stored}**\n"
            )
            if analyzed:
                msg += f"- Vision-Analysen: **{analyzed}**\n"
            if s_errors:
                msg += f"\n⚠️ Scraper-Fehler: {len(s_errors)}"
            if v_errors:
                msg += f"\n⚠️ Vision-Fehler: {len(v_errors)}"
            if db_errors:
                msg += f"\n⚠️ Datenbank-Fehler: {len(db_errors)}"

            msg += "\n\nFrage mich jetzt nach Angeboten, z.B. *'Zeig mir Laptops unter 500 Euro'*"

        return {"final_response": msg}

    # ── Unknown intent ────────────────────────────────────────────────────────
    return {
        "final_response": (
            "Ich habe deine Anfrage nicht verstanden. Versuche es z.B. mit:\n"
            "- *'Lade neue Angebote'*\n"
            "- *'Zeig mir Fernseher unter 300 Euro'*\n"
            "- *'Vergleiche die Laptop-Angebote'*\n"
            "- *'Benachrichtige mich bei Kaffeemaschinen mit 20% Rabatt'*"
        )
    }
