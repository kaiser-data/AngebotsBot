"""Unit tests for scraper utilities."""

import pytest
from scraper.utils import fingerprint_url, clean_price, clean_discount, canonical_url


def test_fingerprint_url_is_deterministic():
    url = "https://www.kaufda.de/angebote/laptop-123"
    assert fingerprint_url(url) == fingerprint_url(url)
    assert len(fingerprint_url(url)) == 16


def test_fingerprint_url_normalizes():
    a = fingerprint_url("https://www.kaufda.de/angebote/laptop-123/")
    b = fingerprint_url("https://www.kaufda.de/angebote/laptop-123")
    assert a == b


def test_clean_price_german_format():
    assert clean_price("1.299,99 €") == 1299.99
    assert clean_price("299,00€")    == 299.0
    assert clean_price("ab 19 EUR")  == 19.0
    assert clean_price(None) is None
    assert clean_price("keine Info") is None


def test_clean_discount():
    assert clean_discount("-38%") == 38.0
    assert clean_discount("38 %") == 38.0
    assert clean_discount(None)   is None


def test_canonical_url_relative():
    base = "https://www.kaufda.de/kategorie/elektronik"
    assert canonical_url(base, "/angebote/item") == "https://www.kaufda.de/angebote/item"


def test_canonical_url_absolute():
    base = "https://www.kaufda.de"
    full = "https://www.amazon.de/item/123"
    assert canonical_url(base, full) == full
