"""Unit tests for agents.response_node."""

from agents.response_node import response_node


def test_response_node_passthrough_when_final_response_already_present():
    result = response_node({"intent": "query", "final_response": "Bereits gesetzt"})
    assert result == {}


def test_response_node_scrape_empty_summary():
    result = response_node(
        {
            "intent": "scrape",
            "offers_stored": [],
            "scraped_offers": [],
            "analyzed_offers": [],
        }
    )

    assert "Keine neuen Angebote gefunden" in result["final_response"]


def test_response_node_scrape_success_with_error_counts():
    result = response_node(
        {
            "intent": "scrape",
            "offers_stored": [{"id": 1}, {"id": 2}],
            "scraped_offers": [{"id": 1}, {"id": 2}, {"id": 3}],
            "analyzed_offers": [{"id": 1}],
            "scrape_errors": ["a", "b"],
            "vision_errors": ["c"],
            "db_errors": ["d", "e", "f"],
        }
    )

    out = result["final_response"]
    assert "**Scraping abgeschlossen!**" in out
    assert "Angebote gefunden: **3**" in out
    assert "Vision-Analysen: **1**" in out
    assert "In Datenbank gespeichert: **2**" in out
    assert "⚠️ Scraper-Fehler: 2" in out
    assert "⚠️ Vision-Fehler: 1" in out
    assert "⚠️ Datenbank-Fehler: 3" in out


def test_response_node_unknown_intent_returns_help():
    result = response_node({"intent": "unknown"})
    assert "Ich habe deine Anfrage nicht verstanden" in result["final_response"]
    assert "Vergleiche die Laptop-Angebote" in result["final_response"]
