"""Unit tests for agents.scraper_node."""

from unittest.mock import AsyncMock, MagicMock, patch

from agents.scraper_node import scraper_node


def test_scraper_node_uses_kaufda_json_scraper():
    offers = [{"external_id": "1", "title": "Milch", "url": "https://x"}]
    errors = ["kw: boom"]

    mock_scraper = MagicMock()
    mock_scraper.scrape_all = AsyncMock(return_value=(offers, errors))

    with patch("agents.scraper_node.KaufdaJsonScraper", return_value=mock_scraper) as ctor:
        result = scraper_node({"user_query": "Lade neue Angebote", "intent": "scrape"})

    ctor.assert_called_once()
    mock_scraper.scrape_all.assert_awaited_once()
    assert result == {"scraped_offers": offers, "scrape_errors": errors}


def test_scraper_node_does_not_import_playwright_scraper():
    """Regression: interactive scrape must not use KaufdaScraper."""
    with patch("agents.scraper_node.KaufdaJsonScraper") as ctor:
        ctor.return_value.scrape_all = AsyncMock(return_value=([], []))
        with patch.dict("sys.modules", {"scraper.kaufda": MagicMock()}):
            scraper_node({"user_query": "scrape", "intent": "scrape"})
        # KaufdaJsonScraper is the only scraper constructed
        ctor.assert_called_once()
