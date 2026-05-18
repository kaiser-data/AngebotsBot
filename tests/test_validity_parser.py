"""Regression tests for offer validity parsing."""

import json
from datetime import date
from pathlib import Path

from scraper.utils import parse_offer_validity, format_validity_window


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "validity_cases.json"


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_validity_cases_fixture_shape():
    cases = _load_cases()
    assert cases, "Fixture file should contain at least one regression case."
    for case in cases:
        assert "id" in case
        assert "raw_text" in case
        assert "reference_date" in case
        assert "expected" in case


def test_parse_offer_validity_regression_cases():
    for case in _load_cases():
        reference_date = date.fromisoformat(case["reference_date"])
        parsed = parse_offer_validity(case["raw_text"], reference_date=reference_date)
        assert parsed == case["expected"], case["id"]


def test_format_validity_window():
    offer = {
        "valid_from": "2026-05-21",
        "valid_to": "2026-05-24",
        "is_upcoming": True,
        "validity_text": "ab Donnerstag",
    }
    assert format_validity_window(offer) == "Gültig 2026-05-21 bis 2026-05-24"
