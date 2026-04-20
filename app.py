"""
AngebotsBot — Chainlit web application.

Start with:  chainlit run app.py
"""

import asyncio
import logging
import uuid
from typing import Optional

import chainlit as cl
from chainlit.input_widget import Select, TextInput

from workflow import build_graph, AgentState
from tools.alert_tool import get_or_create_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Hintergrund-Services (einmalig) ──────────────────────────────────────────

_background_tasks: list[asyncio.Task] = []
_started = False


async def _start_background_services():
    global _started
    if _started:
        return
    _started = True
    loop = asyncio.get_event_loop()
    try:
        from scheduler.jobs import start_scheduler
        _background_tasks.append(loop.create_task(start_scheduler()))
        logger.info("Scheduler gestartet.")
    except Exception as exc:
        logger.warning("Scheduler konnte nicht gestartet werden: %s", exc)
    try:
        from bot.telegram_bot import start_telegram_bot
        _background_tasks.append(loop.create_task(start_telegram_bot()))
        logger.info("Telegram-Bot gestartet.")
    except Exception as exc:
        logger.warning("Telegram-Bot konnte nicht gestartet werden: %s", exc)


# ── Graph (einmal pro Session) ────────────────────────────────────────────────

def _get_or_build_graph():
    try:
        return build_graph()
    except Exception as exc:
        logger.error("build_graph() fehlgeschlagen: %s", exc)
        return None


# ── Chainlit Hooks ────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start():
    # Graph zuerst bauen — unabhängig von Hintergrundservices
    graph = _get_or_build_graph()
    cl.user_session.set("graph", graph)
    cl.user_session.set("user_id", None)

    # Settings-Panel einrichten
    await cl.ChatSettings(
        [
            TextInput(
                id="telegram_chat_id",
                label="Telegram Chat-ID",
                placeholder="Starte @userinfobot um deine ID zu erhalten",
            ),
            TextInput(
                id="email",
                label="E-Mail-Adresse",
                placeholder="name@beispiel.de",
            ),
            Select(
                id="notification_channel",
                label="Benachrichtigungskanal",
                values=["telegram", "email", "both"],
                initial_value="telegram",
            ),
        ]
    ).send()

    # Hintergrundservices starten (Fehler hier blockieren die UI nicht)
    await _start_background_services()

    status = "✅ Bereit" if graph else "⚠️ Graph-Fehler (siehe Logs)"
    await cl.Message(
        content=(
            f"👋 Willkommen bei **AngebotsBot**! {status}\n\n"
            "Ich durchsuche aktuelle Angebote von kaufda.de mit KI-Bildanalyse.\n\n"
            "**Beispiele:**\n"
            "- *Lade aktuelle Angebote*\n"
            "- *Zeig mir Laptops unter 500 Euro*\n"
            "- *Vergleiche die besten Fernseher-Angebote*\n"
            "- *Benachrichtige mich bei Smartphones mit 30% Rabatt*"
        )
    ).send()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    telegram_id: Optional[str] = settings.get("telegram_chat_id", "").strip() or None
    email: Optional[str]       = settings.get("email", "").strip() or None

    if not telegram_id and not email:
        await cl.Message(content="Bitte gib mindestens eine Kontaktmethode an.").send()
        return

    user = get_or_create_user(telegram_chat_id=telegram_id, email=email)
    if user:
        cl.user_session.set("user_id", user["id"])
        await cl.Message(content="✅ Einstellungen gespeichert!").send()
    else:
        await cl.Message(content="❌ Fehler beim Speichern.").send()


@cl.on_message
async def on_message(message: cl.Message):
    graph   = cl.user_session.get("graph")
    user_id = cl.user_session.get("user_id")

    if graph is None:
        await cl.Message(
            content="⚠️ Graph nicht initialisiert. Bitte die Seite neu laden."
        ).send()
        return

    initial_state: AgentState = {
        "messages":          [],
        "user_query":        message.content,
        "intent":            "unknown",
        "scrape_requested":  False,
        "scraped_offers":    [],
        "scrape_errors":     [],
        "analyzed_offers":   [],
        "vision_errors":     [],
        "offers_stored":     [],
        "db_errors":         [],
        "query_results":     [],
        "comparison_result": "",
        "alert_config":      {"user_id": user_id} if user_id else None,
        "active_alerts":     [],
        "final_response":    "",
        "iteration_count":   0,
    }

    async with cl.Step(name="🤖 Verarbeite Anfrage") as step:
        final_state = initial_state
        try:
            async for event in graph.astream(initial_state):
                node_name = list(event.keys())[0]
                step.output = _node_label(node_name)
                await step.update()
                node_output = list(event.values())[0]
                if node_output:
                    final_state = {**final_state, **node_output}
        except Exception as exc:
            logger.error("Graph-Fehler: %s", exc, exc_info=True)
            await cl.Message(content=f"Fehler: {exc}").send()
            return

    response = final_state.get("final_response") or "Keine Antwort generiert."
    elements: list[cl.Element] = []

    for offer in (final_state.get("query_results") or [])[:6]:
        if offer.get("image_url"):
            elements.append(
                cl.Image(
                    url=offer["image_url"],
                    name=offer.get("title", "")[:30],
                    display="inline",
                    size="small",
                )
            )

    await cl.Message(content=response, elements=elements).send()


def _node_label(node_name: str) -> str:
    return {
        "router_node":     "🧭 Erkenne Anfrage...",
        "scraper_node":    "🕷️ Scanne kaufda.de...",
        "vision_node":     "👁️ Analysiere Produktbilder...",
        "store_node":      "💾 Speichere in Datenbank...",
        "query_node":      "🔍 Suche in Datenbank...",
        "comparison_node": "⚖️ Vergleiche Angebote...",
        "alert_node":      "🔔 Verwalte Alerts...",
        "response_node":   "✍️ Erstelle Antwort...",
    }.get(node_name, f"⏳ {node_name}...")
