"""Branch-coverage tests for agents.query_node.query_node()."""

from unittest.mock import MagicMock, patch

from agents.query_node import query_node


def _state(user_query: str) -> dict:
    return {"user_query": user_query}


def test_empty_query_returns_prompt():
    result = query_node(_state(""))
    assert result["query_results"] == []
    assert "konkrete Frage" in result["final_response"]


def test_missing_user_query_key_returns_prompt():
    result = query_node({})
    assert result["query_results"] == []
    assert "konkrete Frage" in result["final_response"]


@patch("agents.query_node.search_brochure_pages")
@patch("agents.query_node.latest_brochure_pages")
def test_brochure_query_uses_search_then_fallback(latest_b, search_b):
    search_b.return_value = []
    latest_b.return_value = [
        {
            "store": "Lidl",
            "brochure_title": "Lidl KW20",
            "page_number": 3,
            "url": "https://x.de/p1",
            "validity_text": "gültig bis Sa.",
        }
    ]
    result = query_node(_state("zeige mir den lidl prospekt"))
    search_b.assert_called_once()
    latest_b.assert_called_once()
    assert len(result["query_results"]) == 1
    assert "Lidl KW20" in result["final_response"]
    assert "Quellen" in result["final_response"]


@patch("agents.query_node.search_brochure_pages", return_value=[])
@patch("agents.query_node.latest_brochure_pages", return_value=[])
def test_brochure_query_empty_returns_friendly_message(_lb, _sb):
    result = query_node(_state("zeige prospekte"))
    assert result["query_results"] == []
    assert "keine passenden Prospektseiten" in result["final_response"]


@patch("agents.query_node.search_brochure_pages")
@patch("agents.query_node.latest_brochure_pages")
def test_brochure_query_passes_store_filters(latest_b, search_b):
    search_b.return_value = [{"store": "Lidl", "url": "https://x.de/1"}]
    latest_b.return_value = []
    query_node(_state("lidl und aldi prospekt"))
    kwargs = search_b.call_args.kwargs
    assert set(kwargs["stores"]) == {"lidl", "aldi"}


@patch("agents.query_node.latest_offers")
def test_generic_current_offers_query_uses_latest(latest):
    latest.return_value = []  # both calls return empty; falls through to no-results branch
    result = query_node(_state("was ist gerade im angebot"))
    # called twice: only_current=True then only_current=False
    assert latest.call_count == 2
    assert latest.call_args_list[0].kwargs == {"limit": 8, "only_current": True}
    assert latest.call_args_list[1].kwargs == {"limit": 8, "only_current": False}
    assert "keine passenden Angebote" in result["final_response"]


@patch("agents.query_node.get_llm")
@patch("agents.query_node.semantic_search")
def test_specific_query_invokes_llm_with_offers(sem, get_llm):
    sem.return_value = [
        {
            "title": "Bio Apfel",
            "price": 1.99,
            "original_price": 2.49,
            "discount_percent": 20,
            "store": "Edeka",
            "key_features": ["Bio", "Region", "1kg"],
            "deal_verdict": "Sehr gut",
            "url": "https://x.de/apfel",
            "valid_from": "2026-05-16",
            "valid_to": "2026-05-18",
        }
    ]
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Empfehlung: Bio Apfel ist top.")
    get_llm.return_value = llm

    result = query_node(_state("günstige bio äpfel unter 3 euro"))

    sem.assert_called_once()
    assert sem.call_args.kwargs["max_price"] == 3.0
    assert result["final_response"].startswith("Empfehlung: Bio Apfel ist top.")
    assert "Quellen" in result["final_response"]
    assert "https://x.de/apfel" in result["final_response"]


@patch("agents.query_node.get_llm")
@patch("agents.query_node.latest_offers")
@patch("agents.query_node.semantic_search", return_value=[])
def test_specific_query_falls_back_to_latest_when_angebot_keyword(sem, latest, get_llm):
    latest.return_value = [
        {"title": "Käse", "price": 2.99, "url": "https://x.de/k", "store": "Aldi"}
    ]
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Käse-Empfehlung")
    get_llm.return_value = llm

    result = query_node(_state("welche angebote unter 5 euro?"))
    sem.assert_called_once()
    latest.assert_called_once_with(limit=8, only_current=True)
    assert "Käse-Empfehlung" in result["final_response"]


@patch("agents.query_node.latest_offers")
@patch("agents.query_node.semantic_search", return_value=[])
def test_specific_query_without_angebot_keyword_skips_fallback(sem, latest):
    result = query_node(_state("biotee"))
    sem.assert_called_once()
    latest.assert_not_called()
    assert "keine passenden Angebote" in result["final_response"]


@patch("agents.query_node.get_llm")
@patch("agents.query_node.semantic_search")
def test_llm_failure_returns_graceful_fallback(sem, get_llm):
    sem.return_value = [
        {"title": "Brot", "url": "https://x.de/b", "store": "Lidl", "price": 1.49}
    ]
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("api down")
    get_llm.return_value = llm

    result = query_node(_state("brot kaufen"))
    assert "1 passende Angebote" in result["final_response"]
    assert "Quellen" in result["final_response"]


@patch("agents.query_node.get_llm")
@patch("agents.query_node.semantic_search")
def test_no_url_offers_skip_sources_block(sem, get_llm):
    sem.return_value = [{"title": "Honig", "store": "Rewe"}]
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Antwort")
    get_llm.return_value = llm

    result = query_node(_state("honig"))
    assert result["final_response"].strip() == "Antwort"
    assert "Quellen" not in result["final_response"]
