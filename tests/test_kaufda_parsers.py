"""Unit tests for pure static parsers on KaufdaScraper."""

from scraper.kaufda import KaufdaScraper


def test_title_from_alt_strips_kaufda_suffix():
    alt = "Bio Cheddar 200g bei Lidl im Prospekt Woche 20"
    assert KaufdaScraper._title_from_alt(alt) == "Bio Cheddar 200g"


def test_title_from_alt_returns_full_alt_when_no_suffix():
    assert KaufdaScraper._title_from_alt("Frischer Apfel") == "Frischer Apfel"


def test_title_from_alt_handles_none_and_empty():
    assert KaufdaScraper._title_from_alt(None) is None
    assert KaufdaScraper._title_from_alt("") is None


def test_title_from_alt_trims_whitespace():
    assert KaufdaScraper._title_from_alt("   Käse   ") == "Käse"


def test_extract_original_price_statt():
    assert KaufdaScraper._extract_original_price("statt 9,99 €") == 9.99


def test_extract_original_price_war_case_insensitive():
    assert KaufdaScraper._extract_original_price("WAR 12,49 €") == 12.49


def test_extract_original_price_thousands_separator():
    assert KaufdaScraper._extract_original_price("statt 1.299,00 €") == 1299.00


def test_extract_original_price_returns_none_when_absent():
    assert KaufdaScraper._extract_original_price("nur 7,49 €") is None
    assert KaufdaScraper._extract_original_price(None) is None
    assert KaufdaScraper._extract_original_price("") is None


def test_slug_from_url_extracts_last_segment():
    assert (
        KaufdaScraper._slug_from_url("https://www.kaufda.de/Angebote/Lebensmittel")
        == "Lebensmittel"
    )


def test_slug_from_url_strips_trailing_slash():
    assert (
        KaufdaScraper._slug_from_url("https://www.kaufda.de/Angebote/Lebensmittel/")
        == "Lebensmittel"
    )


def test_slug_from_url_returns_none_for_short_urls():
    assert KaufdaScraper._slug_from_url("https://www.kaufda.de/") is None
    assert KaufdaScraper._slug_from_url("https://www.kaufda.de") is None
