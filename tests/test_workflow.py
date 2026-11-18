"""Integration-style tests for the LangGraph router node (no external calls)."""

import pytest
from unittest.mock import patch, MagicMock
from agents.router import router_node

KNOWN_INTENTS = (
    "scrape",
    "query",
    "compare",
    "set_alert",
    "list_alerts",
    "delete_alert",
)


@pytest.mark.parametrize("query,expected_intent", [
    ("Lade aktuelle Angebote",                         "scrape"),
    ("Neue Angebote bitte",                             "scrape"),
    ("aktualisiere die Angebote",                       "scrape"),
    ("Vergleiche die Laptop-Angebote",                  "compare"),
    ("Unterschied zwischen den Fernsehern",             "compare"),
    ("Welche ist besser, A oder B?",                    "compare"),
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
        mock_llm.assert_not_called()


def test_router_welche_angebote_is_not_compare():
    """Bare 'welch*' must not force compare — that's a normal query."""
    mock_response = MagicMock()
    mock_response.content = '{"intent": "query"}'

    with patch("agents.router.get_llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = router_node({
            "user_query": "Welche Angebote gibt es bei Lidl?",
            "messages": [],
        })
        assert result["intent"] == "query"


@pytest.mark.parametrize("intent", KNOWN_INTENTS)
def test_router_preserves_preset_intent_without_llm(intent):
    """Telegram/command paths set intent already — skip re-classification."""
    with patch("agents.router.get_llm") as mock_llm:
        result = router_node({
            "user_query": "Welche Angebote gibt es?",
            "intent": intent,
            "messages": [],
        })
        assert result == {"intent": intent}
        mock_llm.assert_not_called()


def test_router_unknown_preset_still_classifies():
    mock_response = MagicMock()
    mock_response.content = '{"intent": "query"}'

    with patch("agents.router.get_llm") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = router_node({
            "user_query": "Was gibt es Günstiges?",
            "intent": "unknown",
            "messages": [],
        })
        assert result["intent"] == "query"
        mock_llm.assert_called_once()


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
