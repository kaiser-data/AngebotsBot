"""Scraper node — runs KaufdaJsonScraper (httpx) and populates scraped_offers."""

import asyncio
import logging

from scraper.kaufda_json import KaufdaJsonScraper
from workflow.state import AgentState

logger = logging.getLogger(__name__)


def scraper_node(state: AgentState) -> dict:
    """Synchronous wrapper around the async KaufdaJsonScraper.

    Uses the same httpx/JSON path as the daily cron (`scripts/run_scrape.py`)
    instead of Playwright — cheaper and covers the full keyword index.
    """
    logger.info("Scraper node: starting kaufda.de JSON scrape...")
    scraper = KaufdaJsonScraper()

    try:
        # LangGraph nodes are sync; Chainlit/Telegram already have a running loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            offers, errors = asyncio.run(scraper.scrape_all())
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, scraper.scrape_all())
                offers, errors = future.result(timeout=600)

    except Exception as exc:
        logger.error("Scraper node failed: %s", exc)
        return {
            "scraped_offers": [],
            "scrape_errors": [str(exc)],
        }

    logger.info("Scraper node: found %d offers, %d errors", len(offers), len(errors))
    return {
        "scraped_offers": offers,
        "scrape_errors":  errors,
    }
