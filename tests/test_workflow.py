"""Integration-style tests for the LangGraph router node (no external calls)."""

import pytest
from unittest.mock import patch, MagicMock
from agents.router import router_node


@pytest.mark.parametrize("query,expected_intent", [
    ("Lade aktuelle Angebote",                         "scrape"),
    ("Neue Angebote bitte",                             "scrape"),
    ("aktualisiere die Angebote",                       "scrape"),
    ("Vergleiche die Laptop-Angebote",                  "compare"),
    ("Unterschied zwischen den Fernsehern",             "compare"),
    ("Benachrichtige mich bei Smartphones",             "set_alert"),
    ("Alert einrichten für Kaffeemaschinen",            "set_alert"),
    ("Zeige meine Alerts",                              "list_alerts"),
    ("Meine Benachrichtigungen anzeigen",               "list_alerts"),
    ("Lösche meinen Laptop-Alert",                      "delete_alert"),
])
def test_router_heuristics(query, expected_intent):
    """Test that the fast heuristic shortcuts work without LLM calls."""
    with patch("agents.router.get_llm") as mock_llm:
        result = router_node({"user_query": query, "messages": []})
        # Heuristic should fire before LLM is called for these queries
        assert result["intent"] == expected_intent, (
            f"Query '{query}': expected '{expected_intent}', got '{result['intent']}'"
        )


def test_router_empty_query():
    result = router_node({"user_query": "", "messages": []})
    assert result["intent"] == "unknown"


def test_router_llm_fallback():
    """Ambiguous query should fall through to LLM classification."""
    mock_response = MagicMock()
    mock_response.content = '{"intent": "query"}'

    with patch("agents.router.get_llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = router_node({
            "user_query": "Was gibt es Günstiges?",
            "messages": [],
        })
        assert result["intent"] == "query"
