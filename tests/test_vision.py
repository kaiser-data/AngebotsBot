"""Unit tests for vision node JSON parsing."""

import pytest
from agents.vision_node import _parse_json_response, _build_analyzed_offer
from workflow.state import OfferData


SAMPLE_OFFER: OfferData = {
    "external_id":    "abc123",
    "title":          "Samsung Galaxy S24",
    "url":            "https://kaufda.de/test",
    "image_url":      "https://example.com/img.jpg",
    "price":          599.0,
    "original_price": 899.0,
    "discount_percent": 33.0,
    "store":          "MediaMarkt",
    "category":       "elektronik",
    "scraped_at":     "2025-01-01T00:00:00",
}

VALID_JSON = """{
  "product_name": "Samsung Galaxy S24 Ultra",
  "brand": "Samsung",
  "condition": "neu",
  "key_features": ["5G", "200MP Kamera"],
  "quality_score": 0.88,
  "deal_verdict": "Sehr gut",
  "tags": ["smartphone", "samsung"]
}"""

WRAPPED_JSON = "Hier ist meine Analyse:\n" + VALID_JSON + "\nDas war das Ergebnis."


def test_parse_valid_json():
    result = _parse_json_response(VALID_JSON)
    assert result is not None
    assert result["brand"] == "Samsung"
    assert result["quality_score"] == 0.88


def test_parse_json_with_surrounding_text():
    result = _parse_json_response(WRAPPED_JSON)
    assert result is not None
    assert result["deal_verdict"] == "Sehr gut"


def test_parse_invalid_json():
    assert _parse_json_response("Das ist kein JSON") is None
    assert _parse_json_response("") is None


def test_build_analyzed_offer():
    data = _parse_json_response(VALID_JSON)
    analyzed = _build_analyzed_offer(SAMPLE_OFFER, data, VALID_JSON)
    assert analyzed["external_id"]  == "abc123"
    assert analyzed["brand"]        == "Samsung"
    assert analyzed["quality_score"] == 0.88
    assert analyzed["deal_verdict"] == "Sehr gut"
    assert "5G" in analyzed["key_features"]
