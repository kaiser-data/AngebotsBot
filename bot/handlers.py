"""Telegram command and message handlers."""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from workflow import build_graph, AgentState
from tools.alert_tool import get_or_create_user, list_alerts, delete_alert
from bot.formatters import offers_list_html, comparison_table_html

logger = logging.getLogger(__name__)

# Shared graph instance (initialized in telegram_bot.py)
_graph = None


def set_graph(graph) -> None:
    global _graph
    _graph = graph


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Register user and show help."""
    chat_id = str(update.effective_chat.id)
    user = get_or_create_user(telegram_chat_id=chat_id)

    if user:
        ctx.user_data["user_id"] = user["id"]
        welcome = (
            "👋 Willkommen bei <b>AngebotsBot</b>!\n\n"
            "Ich scanne kaufda.de und informiere dich über die besten Deals.\n\n"
            "<b>Befehle:</b>\n"
            "/suche &lt;Suchbegriff&gt; — Angebote suchen\n"
            "/vergleiche &lt;Begriff&gt; — Angebote vergleichen\n"
            "/alert &lt;Name&gt; | &lt;Suche&gt; — Alert einrichten\n"
            "/meinalerts — Meine Alerts anzeigen\n"
            "/neuerangebote — Jetzt Angebote laden\n\n"
            "Oder schreib mir einfach, was du suchst! 🛍️"
        )
    else:
        welcome = "❌ Registrierung fehlgeschlagen. Bitte versuche es erneut."

    await update.message.reply_html(welcome)


async def cmd_suche(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for offers matching a query."""
    query = " ".join(ctx.args) if ctx.args else ""
    if not query:
        await update.message.reply_text("Bitte gib einen Suchbegriff an. Beispiel: /suche Laptop")
        return

    await _run_graph_and_reply(update, ctx, query, intent="query")


async def cmd_vergleiche(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Compare offers matching a query."""
    query = " ".join(ctx.args) if ctx.args else ""
    if not query:
        await update.message.reply_text("Beispiel: /vergleiche Kopfhörer")
        return

    await _run_graph_and_reply(update, ctx, query, intent="compare")


async def cmd_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new alert. Usage: /alert Name | Suchanfrage"""
    user_id = _get_user_id(update, ctx)
    if not user_id:
        await update.message.reply_text("Starte zuerst mit /start.")
        return

    text = " ".join(ctx.args) if ctx.args else ""
    if not text:
        await update.message.reply_html(
            "Beispiel: /alert Laptop-Deal | Laptop unter 500 Euro\n"
            "Format: <b>Name | Suchanfrage</b>"
        )
        return

    await _run_graph_and_reply(
        update, ctx, text, intent="set_alert", user_id=user_id
    )


async def cmd_meinalerts(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """List the user's active alerts."""
    user_id = _get_user_id(update, ctx)
    if not user_id:
        await update.message.reply_text("Starte zuerst mit /start.")
        return

    alerts = list_alerts(user_id)
    if not alerts:
        await update.message.reply_text("Du hast noch keine aktiven Alerts.")
        return

    lines = ["<b>Deine aktiven Alerts:</b>\n"]
    for a in alerts:
        price = f" | max €{a['max_price']:.0f}" if a.get("max_price") else ""
        lines.append(f"• <b>{a['name']}</b>: {a['query_text']}{price}")

    await update.message.reply_html("\n".join(lines))


async def cmd_neuerangebote(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger a scrape run."""
    msg = await update.message.reply_text("🕷️ Scanne kaufda.de... Das kann einige Minuten dauern.")
    await _run_graph_and_reply(update, ctx, "Lade neue Angebote", intent="scrape",
                               edit_message=msg)


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-text messages — route through the full graph."""
    query = update.message.text or ""
    await _run_graph_and_reply(update, ctx, query)


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _run_graph_and_reply(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    query: str,
    intent: Optional[str] = None,
    user_id: Optional[str] = None,
    edit_message=None,
) -> None:
    """Run the LangGraph workflow and send the response to Telegram."""
    if _graph is None:
        await update.message.reply_text("Bot noch nicht bereit. Bitte warte kurz.")
        return

    resolved_user_id = user_id or _get_user_id(update, ctx)

    state: AgentState = {
        "messages":        [],
        "user_query":      query,
        "intent":          intent or "unknown",
        "scrape_requested": intent == "scrape",
        "scraped_offers":  [],
        "scrape_errors":   [],
        "analyzed_offers": [],
        "vision_errors":   [],
        "offers_stored":   [],
        "db_errors":       [],
        "query_results":   [],
        "comparison_result": "",
        "alert_config":    {"user_id": resolved_user_id} if resolved_user_id else None,
        "active_alerts":   [],
        "final_response":  "",
        "iteration_count": 0,
    }

    try:
        result = await _graph.ainvoke(state)
    except Exception as exc:
        logger.error("Graph error in Telegram handler: %s", exc)
        await update.message.reply_text(f"Fehler: {exc}")
        return

    response_text = result.get("final_response", "Keine Antwort generiert.")
    query_results = result.get("query_results", [])

    # For compare, use HTML card format; for query, append offer cards
    if result.get("intent") == "compare" and query_results:
        formatted = comparison_table_html(query_results[:6])
    elif query_results:
        formatted = response_text + "\n\n" + offers_list_html(query_results[:5])
    else:
        formatted = response_text

    # Truncate to Telegram's 4096 char limit
    if len(formatted) > 4000:
        formatted = formatted[:3990] + "\n…"

    if edit_message:
        await edit_message.edit_text(formatted, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(formatted)


def _get_user_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    """Return the DB user_id for this Telegram chat, creating the user if needed."""
    if "user_id" in ctx.user_data:
        return ctx.user_data["user_id"]

    chat_id = str(update.effective_chat.id)
    user = get_or_create_user(telegram_chat_id=chat_id)
    if user:
        ctx.user_data["user_id"] = user["id"]
        return user["id"]
    return None
