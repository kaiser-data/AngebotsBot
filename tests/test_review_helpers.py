"""Unit tests for bot.review_helpers."""

from bot.review_helpers import (
    DEFAULT_REVIEW_STORES,
    _extract_json_object,
    _extract_review_mode,
    _extract_review_store_filters,
    _format_review_card_content,
    _is_review_request,
)


def test_is_review_request_slash_command():
    assert _is_review_request("/review") is True
    assert _is_review_request("hallo /review bitte") is True


def test_is_review_request_german_phrases():
    assert _is_review_request("bitte review kataloge") is True
    assert _is_review_request("prüfe die kataloge") is True
    assert _is_review_request("pruef katalog") is True


def test_is_review_request_typo_tolerated():
    assert _is_review_request("reviewv kataloge") is True


def test_is_review_request_rejects_unrelated():
    assert _is_review_request("aktuelle angebote bei lidl") is False
    assert _is_review_request("review") is False
    assert _is_review_request("kataloge") is False
    assert _is_review_request("") is False


def test_extract_review_store_filters_detects_subset():
    assert _extract_review_store_filters("nur lidl bitte") == ["lidl"]
    assert _extract_review_store_filters("lidl und aldi") == ["lidl", "aldi"]


def test_extract_review_store_filters_defaults_when_no_match():
    assert _extract_review_store_filters("egal welcher shop") == list(DEFAULT_REVIEW_STORES)
    assert _extract_review_store_filters("") == list(DEFAULT_REVIEW_STORES)


def test_extract_review_mode_default_auto():
    assert _extract_review_mode("review kataloge") == "auto"
    assert _extract_review_mode("") == "auto"


def test_extract_review_mode_manual_german_and_english():
    assert _extract_review_mode("manuell prüfen") == "manual"
    assert _extract_review_mode("manual review") == "manual"


def test_extract_json_object_picks_first_brace_block():
    raw = 'Vor dem JSON: {"a": 1, "b": [2, 3]} nach dem JSON'
    assert _extract_json_object(raw) == {"a": 1, "b": [2, 3]}


def test_extract_json_object_returns_none_on_invalid():
    assert _extract_json_object("kein json hier") is None
    assert _extract_json_object("{ broken json") is None


def test_format_review_card_offer_branch():
    offer = {
        "title": "Cheddar 200g",
        "store": "Lidl",
        "price": 2.49,
        "validity_text": "bis Samstag",
        "url": "https://kaufda.de/o/1",
    }
    analysis = {
        "product_name": "Cheddar Käse",
        "brand": "Milbona",
        "condition": "neu",
        "deal_verdict": "Sehr gut",
        "key_features": ["200g", "Schnittkäse", "Milbona", "Aktion", "extra"],
    }
    out = _format_review_card_content(offer, analysis, position=1, total=3)
    assert "**Review 1/3**" in out
    assert "Cheddar 200g" in out
    assert "Cheddar Käse" in out
    assert "Sehr gut" in out
    assert "200g, Schnittkäse, Milbona, Aktion" in out
    assert "extra" not in out.split("Features:")[1]
    assert "https://kaufda.de/o/1" in out


def test_format_review_card_offer_branch_handles_missing():
    out = _format_review_card_content({}, {}, position=2, total=5)
    assert "**Review 2/5**" in out
    assert "Titel: ?" in out
    assert "Features: –" in out


def test_format_review_card_brochure_branch():
    offer = {
        "category": "prospekt",
        "store": "Edeka",
        "brochure_title": "Edeka KW20",
        "page_number": 4,
        "validity_text": "gültig bis 24.05.",
        "url": "https://kaufda.de/p/edeka",
    }
    analysis = {
        "page_summary": "Frische Angebote",
        "comparison_hint": "Preis pro kg vergleichen",
        "top_offers": [
            {"product": "Apfel", "price": "1,99 €", "badge": "kg-Preis"},
            {"product": "Butter", "price": "1,49 €", "badge": ""},
        ],
    }
    out = _format_review_card_content(offer, analysis, position=1, total=2)
    assert "**Prospekt**" in out
    assert "Edeka KW20" in out
    assert "Seite: 4" in out
    assert "Frische Angebote" in out
    assert "- Apfel | 1,99 € | kg-Preis" in out
    assert "- Butter | 1,49 €" in out
    assert "- Butter | 1,49 € |" not in out


def test_format_review_card_brochure_empty_top_offers_fallback():
    offer = {"category": "prospekt", "store": "Aldi"}
    out = _format_review_card_content(offer, {}, position=1, total=1)
    assert "- Keine automatische Erkennung" in out
    assert "Keine automatische Zusammenfassung" in out
    assert "Manuelle Sichtprüfung nutzen" in out
