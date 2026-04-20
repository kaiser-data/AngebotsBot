"""Scraper node — runs KaufdaScraper and populates scraped_offers in state."""

import asyncio
import logging

from scraper.kaufda import KaufdaScraper
from workflow.state import AgentState

logger = logging.getLogger(__name__)


def scraper_node(state: AgentState) -> dict:
    """Synchronous wrapper around the async KaufdaScraper."""
    logger.info("Scraper node: starting kaufda.de scrape...")
    scraper = KaufdaScraper()

    try:
        # Run the async scraper in a new event loop (Chainlit already has one,
        # but LangGraph nodes are called synchronously by default)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We are inside an async context (Chainlit) — schedule as task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, scraper.scrape_new_offers())
                    offers, errors = future.result(timeout=300)
            else:
                offers, errors = loop.run_until_complete(scraper.scrape_new_offers())
        except RuntimeError:
            offers, errors = asyncio.run(scraper.scrape_new_offers())

    except Exception as exc:
        logger.error("Scraper node failed: %s", exc)
        return {
            "scraped_offers": [],
            "scrape_errors": [str(exc)],
        }

    logger.info("Scraper node: found %d new offers, %d errors", len(offers), len(errors))
    return {
        "scraped_offers": offers,
        "scrape_errors":  errors,
    }
