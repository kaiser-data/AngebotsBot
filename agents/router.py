"""Router node — classifies user intent into a structured IntentType."""

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from providers.llm import get_llm
from workflow.state import AgentState

logger = logging.getLogger(__name__)

KNOWN_INTENTS = frozenset({
    "scrape",
    "query",
    "compare",
    "set_alert",
    "list_alerts",
    "delete_alert",
})

ROUTER_SYSTEM = """\
Du bist ein Intent-Klassifikator für AngebotsBot, einen deutschen Angebots-Scanner.
Klassifiziere die Nutzeranfrage in GENAU EINEN der folgenden Intents:

- scrape      → Nutzer will neue Angebote laden/aktualisieren
- query       → Nutzer sucht nach bestimmten Angeboten oder fragt danach
- compare     → Nutzer möchte Angebote vergleichen
- set_alert   → Nutzer möchte eine Benachrichtigung/Alert einrichten
- list_alerts → Nutzer möchte seine Alerts sehen
- delete_alert → Nutzer möchte einen Alert löschen
- unknown     → Keiner der oben genannten Intents passt

Antworte NUR als JSON: {"intent": "<intent>"}"""


def router_node(state: AgentState) -> dict:
    """Classify user_query and write intent back to state."""
    # Command paths (Telegram handlers, scheduler) already set a concrete intent —
    # do not spend an LLM call re-classifying.
    preset = state.get("intent")
    if preset in KNOWN_INTENTS:
        return {"intent": preset}

    query = state.get("user_query", "")
    if not query:
        return {"intent": "unknown"}

    # Fast heuristic shortcuts (no LLM call needed)
    q_lower = query.lower()
    if any(w in q_lower for w in ["lade", "aktualisiere", "neue angebote", "scan", "scrape"]):
        return {"intent": "scrape"}
    # Require explicit compare language — bare "welch*" matches normal questions
    # like "Welche Angebote gibt es?" and must not force the compare path.
    if any(w in q_lower for w in ["vergleich", "unterschied", "besser", "welche ist"]):
        return {"intent": "compare"}
    if any(w in q_lower for w in ["benachrichtig", "alert", "erinner", "sobald"]):
        if any(w in q_lower for w in ["lösch", "entfern", "deaktiviere"]):
            return {"intent": "delete_alert"}
        if any(w in q_lower for w in ["zeig", "mein", "list", "übersicht"]):
            return {"intent": "list_alerts"}
        return {"intent": "set_alert"}
    if any(w in q_lower for w in ["meine alerts", "meine benachrichtigung", "alert liste"]):
        return {"intent": "list_alerts"}

    # LLM classification for ambiguous cases
    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke([
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=query),
        ])
        raw = response.content.strip()
        # Extract JSON even if the LLM adds surrounding text
        match = re.search(r'\{[^}]+\}', raw)
        if match:
            data = json.loads(match.group())
            intent = data.get("intent", "unknown")
            if intent in KNOWN_INTENTS:
                return {"intent": intent}
    except Exception as exc:
        logger.warning("Router LLM call failed: %s", exc)

    # Default: treat anything else as a query
    return {"intent": "query"}
