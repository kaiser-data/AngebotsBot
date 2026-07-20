"""Unit tests for the pure price/discount helpers in scraper.kaufda_json."""

from scraper.kaufda_json import (
    IMPLAUSIBLE_DISCOUNT_PCT,
    _compute_discount,
    _extract_taxonomy,
    _item_to_raw_offer,
)


# ── _compute_discount ────────────────────────────────────────────────────────


def test_discount_basic_markdown():
    # 0.99 sale vs 2.79 regular = 64.5% off — a plausible grocery discount.
    assert _compute_discount(0.99, 2.79) == 64.5


def test_discount_none_when_prices_missing():
    assert _compute_discount(None, 2.79) is None
    assert _compute_discount(0.99, None) is None
    assert _compute_discount(0.0, 2.79) is None


def test_discount_none_when_secondary_not_higher():
    # No markdown to speak of when the "original" isn't above the sale price.
    assert _compute_discount(2.79, 2.79) is None
    assert _compute_discount(2.79, 1.99) is None


def test_discount_suppressed_for_price_range():
    # priceRange=True → mainPrice is an "ab X" floor; the delta is not a real
    # discount (glass-set €9.99 vs €182.99 top-of-range).
    assert _compute_discount(9.99, 182.99, is_price_range=True) is None
    # These particular numbers are also >=90%, so they'd be dropped anyway;
    # a mid-range pair proves the flag alone is enough to suppress.
    assert _compute_discount(50.0, 100.0, is_price_range=True) is None
    assert _compute_discount(50.0, 100.0, is_price_range=False) == 50.0


def test_discount_suppressed_when_implausibly_large():
    # €1 phone vs €769 = 99.9% → financing rate, not a markdown.
    assert _compute_discount(1.0, 769.0) is None
    # A value just under the ceiling is still returned.
    just_under = _compute_discount(11.0, 100.0)  # 89.0%
    assert just_under == 89.0
    assert just_under < IMPLAUSIBLE_DISCOUNT_PCT


# ── _item_to_raw_offer (integration of the flag through the mapper) ───────────


def _item(**prices):
    return {
        "id": "abc123",
        "title": "Test",
        "publisherName": "Testmarkt",
        "prices": {
            "mainPrice": prices.get("main"),
            "secondaryPrice": prices.get("sec"),
            "priceRange": prices.get("range", False),
            "conditions": [],
        },
    }


def test_item_mapper_drops_price_range_discount():
    ro = _item_to_raw_offer(_item(main=9.99, sec=182.99, range=True), "Weinglas")
    assert ro is not None
    assert ro.discount_percent is None
    # The prices themselves are still recorded — only the % is withheld.
    assert ro.price == 9.99


def test_item_mapper_keeps_plausible_discount():
    ro = _item_to_raw_offer(_item(main=0.99, sec=2.79), "Butter")
    assert ro is not None
    assert ro.discount_percent == 64.5


# ── _extract_taxonomy ────────────────────────────────────────────────────────


def _path(*names):
    return [{"id": f"DE-{i}", "name": n} for i, n in enumerate(names)]


def test_taxonomy_returns_top_level_and_full_path():
    item = {"categoryPaths": [_path("Lebensmittel und Getränke", "Produkte", "Getränke", "Bier")]}
    top, path = _extract_taxonomy(item)
    assert top == "Lebensmittel und Getränke"
    assert path == "Lebensmittel und Getränke > Produkte > Getränke > Bier"


def test_taxonomy_prefers_the_longest_path():
    # kaufDA commonly returns a short brand path alongside the product path.
    item = {
        "categoryPaths": [
            _path("Möbel und Wohnen", "Marken Möbel und Wohnen", "System Polster"),
            _path("Möbel und Wohnen", "Produkte", "Möbel", "Wohnzimmer", "Ecksofa"),
        ]
    }
    top, path = _extract_taxonomy(item)
    assert top == "Möbel und Wohnen"
    assert path.endswith("Ecksofa")


def test_taxonomy_absent_or_malformed():
    assert _extract_taxonomy({}) == (None, None)
    assert _extract_taxonomy({"categoryPaths": []}) == (None, None)
    assert _extract_taxonomy({"categoryPaths": [[]]}) == (None, None)
    # Nodes without usable names must not produce a bogus path.
    assert _extract_taxonomy({"categoryPaths": [[{"id": "DE-1"}]]}) == (None, None)


def test_item_mapper_populates_taxonomy_fields():
    item = _item(main=0.99, sec=2.79)
    item["categoryPaths"] = [_path("Lebensmittel und Getränke", "Produkte", "Getränke")]
    ro = _item_to_raw_offer(item, "Cola")
    assert ro is not None
    assert ro.kaufda_category == "Lebensmittel und Getränke"
    assert ro.kaufda_category_path.endswith("Getränke")
    # The search keyword stays in `category`, untouched.
    assert ro.category == "Cola"
