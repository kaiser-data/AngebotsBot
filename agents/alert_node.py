"""Alert node — CRUD operations for user-defined saved searches."""

import json
import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from providers.llm import get_llm
from tools.alert_tool import create_alert, list_alerts, delete_alert
from workflow.state import AgentState

logger = logging.getLogger(__name__)

ALERT_EXTRACT_SYSTEM = """\
Extrahiere aus der folgenden Nutzeranfrage die Alert-Parameter als JSON.
Felder:
- name: kurzer, beschreibender Name (max 30 Zeichen)
- query_text: die Suchanfrage (was soll gesucht werden)
- max_price: maximaler Preis in Euro als Zahl oder null
- min_discount: minimaler Rabatt in Prozent als Zahl oder null
- categories: Liste von Kategorien oder null
Antworte NUR als JSON, keine weiteren Erklärungen."""


def _extract_alert_config(query: str) -> dict:
    """Use LLM to parse alert parameters from a natural language query."""
    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke([
            SystemMessage(content=ALERT_EXTRACT_SYSTEM),
            HumanMessage(content=query),
        ])
        raw = response.content.strip()
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            data = json.loads(match.group())
            return data
    except Exception as exc:
        logger.warning("Alert config extraction failed: %s", exc)

    # Fallback: use the raw query as query_text
    return {"name": query[:30], "query_text": query}


def _format_alerts_list(alerts: list[dict]) -> str:
    if not alerts:
        return "Du hast noch keine aktiven Alerts."
    lines = ["**Deine aktiven Alerts:**\n"]
    for a in alerts:
        price_info = f" | Max: €{a['max_price']:.0f}" if a.get("max_price") else ""
        disc_info  = f" | Min: -{a['min_discount']:.0f}%" if a.get("min_discount") else ""
        lines.append(f"- **{a['name']}**: {a['query_text']}{price_info}{disc_info}")
    return "\n".join(lines)


def alert_node(state: AgentState) -> dict:
    """Handle create / list / delete alert operations."""
    intent = state.get("intent", "list_alerts")
    query  = state.get("user_query", "")

    # The Telegram bot sets telegram_chat_id in alert_config;
    # Chainlit users are identified by a session-level user_id stored in alert_config.
    config_data = state.get("alert_config") or {}
    user_id: Optional[str] = config_data.get("user_id")

    if not user_id:
        return {
            "final_response": (
                "Um Alerts zu nutzen, musst du dich zuerst registrieren. "
                "Starte den Telegram-Bot mit /start oder setze deine E-Mail in den Einstellungen."
            )
        }

    # ── List ──────────────────────────────────────────────────────────────────
    if intent == "list_alerts":
        alerts = list_alerts(user_id)
        return {
            "active_alerts": alerts,
            "final_response": _format_alerts_list(alerts),
        }

    # ── Delete ────────────────────────────────────────────────────────────────
    if intent == "delete_alert":
        alert_id = config_data.get("alert_id")
        if not alert_id:
            return {
                "final_response": (
                    "Bitte nenne die ID des Alerts. Deine Alerts: "
                    + _format_alerts_list(list_alerts(user_id))
                )
            }
        success = delete_alert(user_id, alert_id)
        return {
            "final_response": "Alert gelöscht ✓" if success else "Alert konnte nicht gelöscht werden.",
        }

    # ── Create ────────────────────────────────────────────────────────────────
    params = _extract_alert_config(query)
    new_alert = create_alert(
        user_id=user_id,
        name=params.get("name", query[:30]),
        query_text=params.get("query_text", query),
        max_price=params.get("max_price"),
        min_discount=params.get("min_discount"),
        categories=params.get("categories"),
    )

    if new_alert:
        price_info = f" (max €{params['max_price']:.0f})" if params.get("max_price") else ""
        disc_info  = f" (min -{params['min_discount']:.0f}%)" if params.get("min_discount") else ""
        return {
            "alert_config": new_alert,
            "final_response": (
                f"✅ Alert **{new_alert['name']}** wurde erstellt!\n"
                f"Ich benachrichtige dich jeden Montag über neue Angebote "
                f"für: *{params.get('query_text', query)}*{price_info}{disc_info}."
            ),
        }

    return {"final_response": "Alert konnte nicht erstellt werden. Bitte versuche es erneut."}
