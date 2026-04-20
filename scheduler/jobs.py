"""
APScheduler jobs for AngebotsBot.

- weekly_scrape_job  : runs every Monday at 08:00 Europe/Berlin
                       scrapes kaufda.de and triggers the weekly digest

Called via: start_scheduler() from app.py
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from providers.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def weekly_scrape_job() -> None:
    """
    1. Run the full scrape → vision → store pipeline.
    2. Invoke the Supabase weekly-digest Edge Function.
    """
    logger.info("Weekly scrape job started...")

    # Import here to avoid circular imports at module load time
    from workflow import build_graph, AgentState

    graph = build_graph()
    state: AgentState = {
        "messages":        [],
        "user_query":      "Lade neue Angebote",
        "intent":          "scrape",
        "scrape_requested": True,
        "scraped_offers":  [],
        "scrape_errors":   [],
        "analyzed_offers": [],
        "vision_errors":   [],
        "offers_stored":   [],
        "db_errors":       [],
        "query_results":   [],
        "comparison_result": "",
        "alert_config":    None,
        "active_alerts":   [],
        "final_response":  "",
        "iteration_count": 0,
    }

    try:
        result = await graph.ainvoke(state)
        stored = len(result.get("offers_stored", []))
        logger.info("Weekly scrape finished: %d offers stored", stored)
    except Exception as exc:
        logger.error("Weekly scrape job failed: %s", exc)
        return

    # Invoke the Supabase Edge Function to send digests
    await _invoke_weekly_digest_edge_function()


async def _invoke_weekly_digest_edge_function() -> None:
    """Call the Supabase weekly-digest Edge Function via the Python client."""
    try:
        sb = get_supabase()
        # supabase-py v2 functions client
        resp = sb.functions.invoke("weekly-digest", invoke_options={"body": {}})
        logger.info("Weekly digest Edge Function invoked: %s", resp)
    except Exception as exc:
        logger.error("Failed to invoke weekly-digest Edge Function: %s", exc)


async def start_scheduler() -> None:
    """
    Create and start the AsyncIOScheduler.
    Runs the weekly scrape every Monday at SCRAPE_CRON_HOUR:00 (Europe/Berlin).
    This coroutine runs indefinitely.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone=config.APP_TIMEZONE)
    _scheduler.add_job(
        weekly_scrape_job,
        trigger="cron",
        day_of_week=config.SCRAPE_CRON_DAY_OF_WEEK,
        hour=config.SCRAPE_CRON_HOUR,
        minute=0,
        id="weekly_scrape",
        replace_existing=True,
    )
    _scheduler.start()

    logger.info(
        "Scheduler started. Weekly scrape: %s %02d:00 %s",
        config.SCRAPE_CRON_DAY_OF_WEEK.upper(),
        config.SCRAPE_CRON_HOUR,
        config.APP_TIMEZONE,
    )

    # Keep alive until cancelled
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
