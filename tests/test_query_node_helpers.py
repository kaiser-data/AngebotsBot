"""Unit tests for agents.query_node pure helpers."""

from agents.query_node import (
    _extract_price_filter,
    _extract_store_filters,
    _format_source_list,
    _is_brochure_query,
    _is_generic_current_offers_query,
)


def test_extract_price_filter_german_comma():
    assert _extract_price_filter("Käse unter 3,50 Euro") == 3.50


def test_extract_price_filter_with_dot():
    assert _extract_price_filter("Laptop unter 999.00 €") == 999.00


def test_extract_price_filter_bare_number():
    assert _extract_price_filter("unter 10") == 10.0


def test_extract_price_filter_missing():
    assert _extract_price_filter("aktuelle Angebote bei Lidl") is None
    assert _extract_price_filter("") is None


def test_is_generic_current_offers_query_matches():
    for q in (
        "Was ist gerade im Angebot?",
        "aktuelle angebote",
        "Welche Angebote gibt es diese Woche?",
        "Heute im Angebot",
    ):
        assert _is_generic_current_offers_query(q), q


def test_is_generic_current_offers_query_rejects_specific():
    assert not _is_generic_current_offers_query("Käse unter 3 Euro")
    assert not _is_generic_current_offers_query("")


def test_extract_store_filters_picks_known_chains():
    assert _extract_store_filters("Lidl und Aldi Prospekte") == ["lidl", "aldi"]
    assert _extract_store_filters("REWE") == ["rewe"]


def test_extract_store_filters_unknown():
    assert _extract_store_filters("Kaufland Aktion") == []
    assert _extract_store_filters("") == []


def test_is_brochure_query_matches_keywords():
    for q in ("Aktueller Prospekt", "Lidl Katalog", "Seite 3 vom Flyer", "kataloge"):
        assert _is_brochure_query(q), q


def test_is_brochure_query_rejects():
    assert not _is_brochure_query("Käse unter 3 Euro")
    assert not _is_brochure_query("")


def test_format_source_list_renders_markdown_links():
    results = [
        {"brochure_title": "Lidl KW20", "url": "https://x.de/a"},
        {"title": "Aldi Süd", "viewer_url": "https://x.de/b"},
    ]
    out = _format_source_list(results)
    assert "1. [Lidl KW20](https://x.de/a)" in out
    assert "2. [Aldi Süd](https://x.de/b)" in out


def test_format_source_list_skips_entries_without_url():
    results = [
        {"brochure_title": "No link"},
        {"title": "Has link", "url": "https://x.de/c"},
    ]
    out = _format_source_list(results)
    assert "No link" not in out
    assert "[Has link](https://x.de/c)" in out


def test_format_source_list_caps_at_five():
    results = [{"title": f"item {i}", "url": f"https://x.de/{i}"} for i in range(10)]
    out = _format_source_list(results)
    assert out.count("https://x.de/") == 5
    assert "6. " not in out
