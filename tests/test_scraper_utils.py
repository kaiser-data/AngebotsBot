"""Unit tests for scraper.utils pure helpers."""

from scraper.utils import (
    canonical_url,
    clean_discount,
    clean_price,
    extract_loyalty_condition,
    extract_price_candidates,
    extract_source_page_metadata,
    fingerprint_url,
    format_validity_window,
    resolve_offer_prices,
)


def test_fingerprint_url_is_stable_and_canonical():
    a = fingerprint_url("https://www.kaufda.de/foo/bar/")
    b = fingerprint_url("https://www.kaufda.de/foo/bar")
    c = fingerprint_url("HTTPS://WWW.KAUFDA.DE/FOO/BAR")
    assert a == b == c
    assert len(a) == 16


def test_fingerprint_url_differs_for_distinct_urls():
    assert fingerprint_url("https://x.de/a") != fingerprint_url("https://x.de/b")


def test_canonical_url_resolves_relative():
    assert canonical_url("https://x.de/p/", "deal") == "https://x.de/p/deal"


def test_canonical_url_preserves_absolute():
    assert canonical_url("https://x.de/", "https://y.de/z") == "https://y.de/z"


def test_extract_source_page_metadata_parses_page_and_viewer():
    url = "https://www.kaufda.de/contentviewer/abc?page=4"
    meta = extract_source_page_metadata(url)
    assert meta["source_page_number"] == 4
    assert meta["source_viewer_url"] == url


def test_extract_source_page_metadata_handles_missing_and_invalid():
    assert extract_source_page_metadata(None) == {
        "source_viewer_url": None,
        "source_page_number": None,
    }
    meta = extract_source_page_metadata("https://x.de/path?page=abc")
    assert meta["source_page_number"] is None
    assert meta["source_viewer_url"] is None


def test_clean_price_parses_german_format():
    assert clean_price("1.299,99 €") == 1299.99
    assert clean_price("0,99€") == 0.99
    assert clean_price("12,50") == 12.50


def test_clean_price_handles_none_and_garbage():
    assert clean_price(None) is None
    assert clean_price("kein Preis") is None


def test_clean_discount_extracts_percentage():
    assert clean_discount("-38%") == 38.0
    assert clean_discount("Rabatt 15") == 15.0
    assert clean_discount(None) is None


def test_extract_price_candidates_returns_unique_ordered():
    text = "Statt 9,99 € jetzt 7,49 € (mit Lidl Plus 7,49 €)"
    assert extract_price_candidates(text) == [9.99, 7.49]


def test_extract_price_candidates_empty():
    assert extract_price_candidates("") == []
    assert extract_price_candidates(None) == []


def test_extract_loyalty_condition_detects_lidl_plus():
    result = extract_loyalty_condition("Nur mit Lidl Plus App 7,49 €")
    assert result["requires_loyalty"] is True
    assert result["loyalty_program"] == "lidl_plus"
    assert "lidl plus" in result["price_condition_text"].lower()


def test_extract_loyalty_condition_no_match():
    result = extract_loyalty_condition("Frischer Apfel pro kg")
    assert result == {
        "requires_loyalty": False,
        "loyalty_program": None,
        "price_condition_text": None,
    }


def test_extract_loyalty_condition_none_input():
    assert extract_loyalty_condition(None)["requires_loyalty"] is False


def test_resolve_offer_prices_without_loyalty_keeps_primary():
    result = resolve_offer_prices(9.99, "Statt 12,99 € nur 9,99 €", requires_loyalty=False)
    assert result["price"] == 9.99
    assert result["loyalty_price"] is None


def test_resolve_offer_prices_with_loyalty_splits_pair():
    text = "Statt 9,99 € mit Lidl Plus 7,49 €"
    result = resolve_offer_prices(9.99, text, requires_loyalty=True)
    assert result["loyalty_price"] == 7.49
    assert result["standard_price"] == 9.99
    assert result["price"] == 9.99


def test_resolve_offer_prices_with_loyalty_single_price():
    result = resolve_offer_prices(7.49, "Nur mit Lidl Plus 7,49 €", requires_loyalty=True)
    assert result["loyalty_price"] == 7.49
    assert result["standard_price"] is None
    assert result["price"] == 7.49


def test_format_validity_window_range():
    offer = {"valid_from": "2026-05-21", "valid_to": "2026-05-24"}
    assert format_validity_window(offer) == "Gültig 2026-05-21 bis 2026-05-24"


def test_format_validity_window_single_day_current():
    offer = {"valid_from": "2026-05-16", "valid_to": "2026-05-16", "is_upcoming": False}
    assert format_validity_window(offer) == "Gültig am 2026-05-16"


def test_format_validity_window_single_day_upcoming():
    offer = {"valid_from": "2026-05-21", "valid_to": "2026-05-21", "is_upcoming": True}
    assert format_validity_window(offer) == "Gültig ab 2026-05-21"


def test_format_validity_window_only_from():
    assert format_validity_window({"valid_from": "2026-05-16"}) == "Seit 2026-05-16"
    assert (
        format_validity_window({"valid_from": "2026-05-21", "is_upcoming": True})
        == "Gültig ab 2026-05-21"
    )


def test_format_validity_window_only_to():
    assert format_validity_window({"valid_to": "2026-05-18"}) == "Gültig bis 2026-05-18"


def test_format_validity_window_falls_back_to_raw_text():
    assert format_validity_window({"validity_text": "ab Donnerstag"}) == "ab Donnerstag"
    assert format_validity_window({}) is None
