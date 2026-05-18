"""Unit tests for Telegram/HTML formatter helpers."""

from bot.formatters import comparison_table_html, digest_html, offer_card_html, offers_list_html


def test_offer_card_html_renders_core_fields_and_escapes():
    offer = {
        "title": "Fisch & Chips <XXL>",
        "url": "https://x.de/a",
        "store": "Lidl & Co",
        "price": 2.49,
        "original_price": 3.99,
        "discount_percent": 38,
        "deal_verdict": "Sehr gut",
        "key_features": ["Knusprig", "Tiefkuehl", "Schnell"],
        "valid_from": "2026-05-16",
        "valid_to": "2026-05-18",
    }

    out = offer_card_html(offer, index=2)

    assert '2. <a href="https://x.de/a"><b>Fisch &amp; Chips &lt;XXL&gt;</b></a>' in out
    assert "EUR" not in out
    assert "€2.49" in out
    assert "<s>€3.99</s>" in out
    assert "<b>-38%</b>" in out
    assert "🌟 Sehr gut" in out
    assert "📋 Knusprig · Tiefkuehl · Schnell" in out
    assert "🗓️ Gültig 2026-05-16 bis 2026-05-18" in out


def test_offers_list_html_adds_header_and_divider():
    offers = [
        {"title": "A", "url": "https://x.de/a"},
        {"title": "B", "url": "https://x.de/b"},
    ]

    out = offers_list_html(offers, header="Top & Deals")

    assert out.startswith("<b>Top &amp; Deals</b>\n\n1. ")
    assert "─────────────────" in out
    assert '2. <a href="https://x.de/b"><b>B</b></a>' in out


def test_comparison_table_html_renders_fallbacks():
    offers = [
        {
            "title": "Bio Apfel",
            "url": "https://x.de/a",
            "price": 1.99,
            "discount_percent": 20,
            "store": "Edeka",
            "deal_verdict": "Gut",
        },
        {
            "title": "Käse",
            "url": "https://x.de/k",
        },
    ]

    out = comparison_table_html(offers)

    assert "<b>🔍 Angebotsvergleich</b>" in out
    assert "<b>1. Bio Apfel</b>" in out
    assert "💰 €1.99 (-20%) | 🏪 Edeka | ✅ Gut" in out
    assert '<a href="https://x.de/a">Details</a>' in out
    assert "<b>2. Käse</b>" in out
    assert "💰 ? (–) | 🏪 ? |  ?" in out


def test_digest_html_limits_each_section_to_five_offers():
    offers = [{"title": f"Deal {i}", "url": f"https://x.de/{i}"} for i in range(1, 7)]

    out = digest_html([("Liste", offers)])

    assert "🛍️ <b>Dein wöchentlicher Angebots-Digest</b>" in out
    assert "📌 <b>Liste</b>" in out
    assert "Deal 5" in out
    assert "Deal 6" not in out
    assert "────────────────────" in out
