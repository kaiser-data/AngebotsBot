"""Tests for agents.comparison_node."""

from unittest.mock import MagicMock, patch

from agents.comparison_node import _build_comparison_table, comparison_node


def test_build_comparison_table_empty():
    assert _build_comparison_table([]) == ""


def test_build_comparison_table_renders_header_and_rows():
    offers = [
        {
            "title": "Bio Apfel 1kg",
            "url": "https://x.de/a",
            "price": 1.99,
            "discount_percent": 20,
            "store": "Edeka",
            "deal_verdict": "Sehr gut",
        },
        {
            "title": "Käse",
            "url": "https://x.de/k",
            "store": "Lidl",
        },
    ]
    table = _build_comparison_table(offers)
    assert "| # | Produkt | Preis | Rabatt | Shop | Bewertung |" in table
    assert "|---|---------|-------|--------|------|-----------|" in table
    assert "[Bio Apfel 1kg](https://x.de/a)" in table
    assert "€1.99" in table
    assert "-20%" in table
    # row 2 falls back to '?' / '–'
    assert "| 2 | [Käse](https://x.de/k) | ? | – | Lidl | ? |" in table


def test_build_comparison_table_truncates_long_title():
    long_title = "x" * 80
    table = _build_comparison_table([{"title": long_title, "url": "https://x.de/x"}])
    assert ("x" * 40) in table
    assert ("x" * 41) not in table


@patch("agents.comparison_node.fetch_offers_by_keywords", return_value=[])
def test_comparison_node_no_offers(_fetch):
    result = comparison_node({"user_query": "irgendwas"})
    assert result["query_results"] == []
    assert "Keine Angebote zum Vergleichen" in result["final_response"]
    assert result["comparison_result"] == result["final_response"]


@patch("agents.comparison_node.get_llm")
@patch("agents.comparison_node.fetch_offers_by_keywords")
def test_comparison_node_invokes_llm_with_table(fetch, get_llm):
    fetch.return_value = [
        {"title": "A", "price": 1.0, "url": "https://x.de/a", "store": "Lidl"}
    ]
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Mein Urteil: A ist besser.")
    get_llm.return_value = llm

    result = comparison_node({"user_query": "vergleiche A und B"})

    assert result["final_response"] == "Mein Urteil: A ist besser."
    assert result["comparison_result"] == "Mein Urteil: A ist besser."
    assert result["query_results"] == fetch.return_value

    # the LLM should receive the rendered table inside the human message
    human_msg = llm.invoke.call_args.args[0][1]
    assert "[A](https://x.de/a)" in human_msg.content


@patch("agents.comparison_node.get_llm")
@patch("agents.comparison_node.fetch_offers_by_keywords")
def test_comparison_node_llm_failure_falls_back_to_raw_table(fetch, get_llm):
    fetch.return_value = [
        {"title": "Brot", "price": 1.49, "url": "https://x.de/b", "store": "Rewe"}
    ]
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("api down")
    get_llm.return_value = llm

    result = comparison_node({"user_query": "vergleiche brot"})

    assert "[Brot](https://x.de/b)" in result["final_response"]
    assert "| # | Produkt |" in result["final_response"]
    assert result["comparison_result"] == result["final_response"]


@patch("agents.comparison_node.fetch_offers_by_keywords", return_value=[])
def test_comparison_node_missing_user_query_key(_fetch):
    result = comparison_node({})
    assert "Keine Angebote" in result["final_response"]
