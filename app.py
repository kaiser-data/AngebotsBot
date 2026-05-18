"""
AngebotsBot — Chainlit web application.

Start with:  chainlit run app.py
"""

import asyncio
import json
import logging
import os
import re
import sys
import uuid
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import chainlit as cl
import chainlit.socket as cl_socket
from chainlit import Action
from chainlit.input_widget import Select, TextInput

from agents.vision_node import _analyze_batch
from providers.vision import get_vision_client
from providers.supabase_client import get_supabase
from scraper.kaufda import KaufdaScraper
from workflow import build_graph, AgentState
from scheduler.jobs import start_scheduler
from bot.telegram_bot import start_telegram_bot
from bot.review_helpers import (
    DEFAULT_REVIEW_STORES,
    _extract_json_object,
    _extract_review_mode,
    _extract_review_store_filters,
    _format_review_card_content,
    _is_review_request,
)
from tools.alert_tool import get_or_create_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _patch_chainlit_connect_handler() -> None:
    """Accept the optional Socket.IO auth argument used by newer clients."""
    original_connect = cl_socket.connect

    async def compat_connect(sid, environ, auth=None):
        return await original_connect(sid, environ)

    cl_socket.connect = compat_connect
    namespace_handlers = cl_socket.sio.handlers.get("/", {})
    if namespace_handlers.get("connect") is original_connect:
        namespace_handlers["connect"] = compat_connect


_patch_chainlit_connect_handler()

# ── Hintergrund-Services (einmalig) ──────────────────────────────────────────

_background_tasks: list[asyncio.Task] = []
_started = False
REVIEW_BATCH_SIZE = 5
BROCHURE_REVIEW_PROMPT = """\
Analysiere diese deutsche Prospektseite und gib NUR valides JSON zurück.

Ziel:
- kurze Seitenzusammenfassung
- bis zu 5 sichtbare Angebote
- knapper Vergleichshinweis für manuelle Prüfung

JSON-Schema:
{
  "page_summary": "Kurze Zusammenfassung der Seite",
  "top_offers": [
    {
      "product": "Produktname",
      "price": "Preis wie sichtbar",
      "badge": "z.B. Rabatt, kg-Preis, Aktionshinweis oder leer"
    }
  ],
  "comparison_hint": "Worauf ein Mensch bei der Prüfung achten sollte"
}
"""


async def _start_background_services():
    global _started
    if _started:
        return
    _started = True
    loop = asyncio.get_event_loop()
    try:
        _background_tasks.append(loop.create_task(start_scheduler()))
        logger.info("Scheduler gestartet.")
    except Exception as exc:
        logger.warning("Scheduler konnte nicht gestartet werden: %s", exc)
    try:
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
    cl.user_session.set("review_run_id", None)
    cl.user_session.set("review_edit_target", None)
    cl.user_session.set("review_queue", [])
    cl.user_session.set("review_results", [])

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
            "- *Benachrichtige mich bei Smartphones mit 30% Rabatt*\n"
            "- *Review kataloge*"
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
    normalized = message.content.strip().lower()

    if graph is None:
        await cl.Message(
            content="⚠️ Graph nicht initialisiert. Bitte die Seite neu laden."
        ).send()
        return

    if cl.user_session.get("review_edit_target"):
        await _handle_review_edit_message(message.content)
        return

    if _is_review_request(normalized):
        await _start_review_flow(normalized)
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


@cl.action_callback("review_approve")
async def on_review_approve(action: Action):
    await _record_review_decision(action, "approved")


@cl.action_callback("review_reject")
async def on_review_reject(action: Action):
    await _record_review_decision(action, "rejected")


@cl.action_callback("review_flag")
async def on_review_flag(action: Action):
    await _record_review_decision(action, "flagged")


@cl.action_callback("review_skip")
async def on_review_skip(action: Action):
    await _advance_review_queue(action, record_decision=False)


@cl.action_callback("review_edit")
async def on_review_edit(action: Action):
    await _start_review_edit(action)


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


async def _start_review_flow(request_text: str) -> None:
    store_filters = _extract_review_store_filters(request_text)
    review_mode = _extract_review_mode(request_text)
    async with cl.Step(name="🧪 Lade Review-Queue") as step:
        step.output = (
            "Scanne Live-Stichprobe von kaufda.de "
            f"für: {', '.join(store_filters)}..."
        )
        await step.update()

        try:
            scraper = KaufdaScraper()
            offers, scrape_errors = await scraper.scrape_brochure_page_samples(
                retailers=store_filters,
                pages_per_brochure=2,
                max_items=REVIEW_BATCH_SIZE,
            )
            step.output = f"{len(offers)} Prospektseiten gefunden, bereite Review vor..."
            await step.update()
            if review_mode == "auto":
                step.output = "Starte automatische Seitenauswertung..."
                await step.update()
                analyzed, vision_errors = await _analyze_brochure_pages(offers)
            else:
                analyzed = []
                vision_errors = []
        except Exception as exc:
            logger.error("Review-Flow fehlgeschlagen: %s", exc, exc_info=True)
            await cl.Message(content=f"⚠️ Review-Flow fehlgeschlagen: {exc}").send()
            return

    review_queue = _build_review_queue(offers, analyzed)
    review_run_id = str(uuid.uuid4())
    cl.user_session.set("review_run_id", review_run_id)
    cl.user_session.set("review_queue", review_queue)
    cl.user_session.set("review_results", [])
    persisted_pages = _persist_brochure_pages(offers)

    summary_lines = [
        f"Review-Queue erstellt: {len(review_queue)} Angebote.",
        f"Store-Fokus: {', '.join(store_filters)}",
        f"Review-Modus: {review_mode}",
        f"Prospektseiten gespeichert: {persisted_pages}/{len(offers)}",
    ]
    if scrape_errors:
        summary_lines.append(f"Scrape-Fehler: {len(scrape_errors)}")
    if vision_errors:
        summary_lines.append(f"Vision-Fehler: {len(vision_errors)}")
    summary_lines.append("Nutze Approve, Reject, Flag mismatch oder Skip.")
    await cl.Message(content="\n".join(summary_lines)).send()

    await _render_current_review_card()


def _build_review_queue(offers: list[dict], analyzed: list[dict]) -> list[dict]:
    analyzed_by_id = {item["external_id"]: item for item in analyzed}
    queue: list[dict] = []
    for offer in offers:
        queue.append(
            {
                "offer": offer,
                "analysis": analyzed_by_id.get(offer["external_id"]),
            }
        )
    return queue


async def _render_current_review_card() -> None:
    review_queue = cl.user_session.get("review_queue") or []
    review_results = cl.user_session.get("review_results") or []

    if not review_queue:
        await _send_review_summary(review_results)
        return

    current = review_queue[0]
    offer = current["offer"]
    analysis = current.get("analysis") or {}
    position = len(review_results) + 1
    total = len(review_results) + len(review_queue)

    content = _format_review_card_content(offer, analysis, position, total)
    elements: list[cl.Element] = []
    if offer.get("image_url"):
        elements.append(
            cl.Image(
                url=offer["image_url"],
                name=offer.get("title", "offer-image")[:40],
                display="inline",
                size="small",
            )
        )

    payload = json.dumps({"external_id": offer["external_id"]})
    actions = [
        Action(name="review_approve", value=payload, label="Approve"),
        Action(name="review_edit", value=payload, label="Edit"),
        Action(name="review_reject", value=payload, label="Reject"),
        Action(name="review_flag", value=payload, label="Flag mismatch"),
        Action(name="review_skip", value=payload, label="Skip"),
    ]

    await cl.Message(content=content, elements=elements, actions=actions).send()


async def _record_review_decision(action: Action, decision: str) -> None:
    await _advance_review_queue(action, record_decision=True, decision=decision)


async def _start_review_edit(action: Action) -> None:
    review_queue = cl.user_session.get("review_queue") or []
    if not review_queue:
        await action.remove()
        await cl.Message(content="Keine aktive Review-Karte zum Bearbeiten.").send()
        return

    payload = json.loads(action.value)
    current = review_queue[0]
    if payload.get("external_id") != current["offer"]["external_id"]:
        await action.remove()
        await cl.Message(
            content="Diese Edit-Aktion ist veraltet. Nutze die Buttons der neuesten Karte."
        ).send()
        return

    cl.user_session.set("review_edit_target", current["offer"]["external_id"])
    await action.remove()
    await cl.Message(
        content=(
            "Sende jetzt JSON mit den Feldern, die du korrigieren willst.\n\n"
            "Beispiel:\n"
            "```json\n"
            "{\n"
            '  "product_name": "Samsung Galaxy S24 Ultra",\n'
            '  "brand": "Samsung",\n'
            '  "deal_verdict": "Sehr gut",\n'
            '  "key_features": ["5G", "256 GB"]\n'
            "}\n"
            "```\n"
            "Erlaubte Felder: `product_name`, `brand`, `condition`, `deal_verdict`, `key_features`, `quality_score`, `tags`\n"
            "Mit `cancel` brichst du den Edit-Modus ab."
        )
    ).send()


async def _advance_review_queue(
    action: Action,
    record_decision: bool,
    decision: str | None = None,
) -> None:
    review_queue = cl.user_session.get("review_queue") or []
    review_results = cl.user_session.get("review_results") or []
    if not review_queue:
        await action.remove()
        await _send_review_summary(review_results)
        return

    payload = json.loads(action.value)
    current = review_queue.pop(0)
    if payload.get("external_id") != current["offer"]["external_id"]:
        review_queue.insert(0, current)
        cl.user_session.set("review_queue", review_queue)
        await action.remove()
        await cl.Message(
            content="Diese Review-Aktion ist veraltet. Nutze die Buttons der neuesten Karte."
        ).send()
        return

    await action.remove()
    if record_decision:
        persisted = _persist_review_decision(
            review_run_id=cl.user_session.get("review_run_id"),
            user_id=cl.user_session.get("user_id"),
            offer=current["offer"],
            analysis=current.get("analysis") or {},
            decision=decision or "unknown",
        )
        review_results.append(
            {
                "external_id": current["offer"]["external_id"],
                "title": current["offer"].get("title"),
                "decision": decision,
                "image_url": current["offer"].get("image_url"),
                "persisted": persisted,
            }
        )

    cl.user_session.set("review_queue", review_queue)
    cl.user_session.set("review_results", review_results)

    if record_decision:
        await cl.Message(
            content=(
                f"Entscheidung gespeichert: `{decision}` für **{current['offer'].get('title', '?')}**"
                + (" (Supabase)" if review_results[-1].get("persisted") else " (nur Session)")
            )
        ).send()

    await _render_current_review_card()


async def _send_review_summary(review_results: list[dict]) -> None:
    approved = sum(1 for item in review_results if item.get("decision") == "approved")
    rejected = sum(1 for item in review_results if item.get("decision") == "rejected")
    flagged = sum(1 for item in review_results if item.get("decision") == "flagged")
    persisted = sum(1 for item in review_results if item.get("persisted"))

    lines = [
        "Review abgeschlossen.",
        f"Approved: {approved}",
        f"Rejected: {rejected}",
        f"Flagged: {flagged}",
        f"Persistiert: {persisted}/{len(review_results)}",
    ]
    await cl.Message(content="\n".join(lines)).send()


async def _handle_review_edit_message(content: str) -> None:
    target_external_id = cl.user_session.get("review_edit_target")
    review_queue = cl.user_session.get("review_queue") or []

    if not target_external_id or not review_queue:
        cl.user_session.set("review_edit_target", None)
        await cl.Message(content="Edit-Modus wurde beendet.").send()
        return

    if content.strip().lower() == "cancel":
        cl.user_session.set("review_edit_target", None)
        await cl.Message(content="Edit-Modus abgebrochen.").send()
        await _render_current_review_card()
        return

    try:
        patch = json.loads(content)
    except json.JSONDecodeError as exc:
        await cl.Message(
            content=f"Ungültiges JSON: {exc}. Sende gültiges JSON oder `cancel`."
        ).send()
        return

    if not isinstance(patch, dict):
        await cl.Message(content="Edit erwartet ein JSON-Objekt.").send()
        return

    allowed_fields = {
        "product_name",
        "brand",
        "condition",
        "deal_verdict",
        "key_features",
        "quality_score",
        "tags",
    }
    unknown = [key for key in patch.keys() if key not in allowed_fields]
    if unknown:
        await cl.Message(
            content=f"Unbekannte Felder: {', '.join(unknown)}"
        ).send()
        return

    current = review_queue[0]
    if current["offer"]["external_id"] != target_external_id:
        cl.user_session.set("review_edit_target", None)
        await cl.Message(content="Edit-Ziel ist nicht mehr aktuell.").send()
        await _render_current_review_card()
        return

    analysis = dict(current.get("analysis") or {})
    for key, value in patch.items():
        analysis[key] = value
    current["analysis"] = analysis
    review_queue[0] = current
    cl.user_session.set("review_queue", review_queue)
    cl.user_session.set("review_edit_target", None)

    await cl.Message(content="Korrektur übernommen.").send()
    await _render_current_review_card()


def _persist_review_decision(
    review_run_id: str | None,
    user_id: str | None,
    offer: dict,
    analysis: dict,
    decision: str,
) -> bool:
    try:
        get_supabase().table("offer_reviews").insert(
            {
                "review_session_id": review_run_id,
                "reviewer_user_id": user_id,
                "external_id": offer.get("external_id"),
                "offer_url": offer.get("url"),
                "image_url": offer.get("image_url"),
                "scraped_title": offer.get("title"),
                "scraped_store": offer.get("store"),
                "scraped_price": offer.get("price"),
                "validity_text": offer.get("validity_text"),
                "vision_product_name": analysis.get("product_name"),
                "vision_brand": analysis.get("brand"),
                "vision_condition": analysis.get("condition"),
                "vision_key_features": analysis.get("key_features") or [],
                "vision_verdict": analysis.get("deal_verdict"),
                "decision": decision,
            }
        ).execute()
        return True
    except Exception as exc:
        logger.warning("Review-Persistierung fehlgeschlagen: %s", exc)
        return False


def _persist_brochure_pages(offers: list[dict]) -> int:
    brochure_rows = []
    for offer in offers:
        if offer.get("category") != "prospekt":
            continue
        brochure_rows.append(
            {
                "external_id": offer.get("external_id"),
                "store": offer.get("store"),
                "category": offer.get("category") or "prospekt",
                "title": offer.get("title") or "Prospektseite",
                "brochure_title": offer.get("brochure_title"),
                "viewer_url": offer.get("url"),
                "page_number": offer.get("page_number"),
                "image_url": offer.get("image_url"),
                "validity_text": offer.get("validity_text"),
                "valid_from": offer.get("valid_from"),
                "valid_to": offer.get("valid_to"),
                "is_upcoming": bool(offer.get("is_upcoming")),
                "source": "kaufda",
                "scraped_at": offer.get("scraped_at"),
            }
        )

    if not brochure_rows:
        return 0

    try:
        get_supabase().table("brochure_pages").upsert(
            brochure_rows,
            on_conflict="external_id",
        ).execute()
        return len(brochure_rows)
    except Exception as exc:
        logger.warning("Brochure-Page-Persistierung fehlgeschlagen: %s", exc)
        return 0


async def _analyze_brochure_pages(offers: list[dict]) -> tuple[list[dict], list[str]]:
    client = get_vision_client()
    analyzed: list[dict] = []
    errors: list[str] = []

    for offer in offers:
        image_url = offer.get("image_url")
        if not image_url:
            continue
        try:
            response = await client.chat.completions.create(
                model=os.getenv("VISION_MODEL", "gemini-2.5-flash"),
                messages=[
                    {"role": "system", "content": "Antworte nur mit JSON."},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"{BROCHURE_REVIEW_PROMPT}\n\n"
                                    f"Händler: {offer.get('store') or '?'}\n"
                                    f"Prospekt: {offer.get('brochure_title') or offer.get('title') or '?'}\n"
                                    f"Seite: {offer.get('page_number') or '?'}"
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
                        ],
                    },
                ],
                max_tokens=1200,
                temperature=0.1,
            )
            raw = response.choices[0].message.content or ""
            parsed = _extract_json_object(raw) or {}
            analyzed.append(
                {
                    "external_id": offer["external_id"],
                    "page_summary": parsed.get("page_summary", ""),
                    "top_offers": parsed.get("top_offers") or [],
                    "comparison_hint": parsed.get("comparison_hint", ""),
                    "raw_llm_response": raw,
                }
            )
        except Exception as exc:
            errors.append(f"Brochure vision error for {offer.get('external_id')}: {exc}")

    return analyzed, errors


