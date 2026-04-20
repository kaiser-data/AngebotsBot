"""
Telegram bot application — long polling, runs alongside Chainlit.

start_telegram_bot() is called as an asyncio task from app.py.
"""

import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
from workflow import build_graph
from bot.handlers import (
    cmd_start,
    cmd_suche,
    cmd_vergleiche,
    cmd_alert,
    cmd_meinalerts,
    cmd_neuerangebote,
    handle_text,
    set_graph,
)

logger = logging.getLogger(__name__)


async def start_telegram_bot() -> None:
    """
    Build the Telegram Application and start long polling.
    This coroutine runs indefinitely until cancelled.
    """
    logger.info("Starting Telegram bot (long polling)...")

    # Share the LangGraph instance with all handlers
    graph = build_graph()
    set_graph(graph)

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register command handlers
    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("suche",          cmd_suche))
    app.add_handler(CommandHandler("vergleiche",     cmd_vergleiche))
    app.add_handler(CommandHandler("alert",          cmd_alert))
    app.add_handler(CommandHandler("meinalerts",     cmd_meinalerts))
    app.add_handler(CommandHandler("neuerangebote",  cmd_neuerangebote))

    # Free-text fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Initialize and run with long polling (non-blocking for asyncio context)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    logger.info("Telegram bot is running.")

    # Keep this coroutine alive — it will be cancelled on app shutdown
    import asyncio
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Telegram bot shutting down...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
