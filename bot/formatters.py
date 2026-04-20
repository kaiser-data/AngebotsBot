"""Format offer data as Telegram HTML messages."""

from typing import Optional


def offer_card_html(offer: dict, index: Optional[int] = None) -> str:
    """Render a single offer as a Telegram HTML message block."""
    prefix = f"{index}. " if index else ""
    title  = _esc(offer.get("title", "Unbekanntes Angebot"))
    url    = offer.get("url", "")
    store  = _esc(offer.get("store") or "?")

    price_str = f"€{offer['price']:.2f}" if offer.get("price") else "?"
    orig_str  = f" <s>€{offer['original_price']:.2f}</s>" if offer.get("original_price") else ""
    disc_str  = f" <b>-{offer['discount_percent']:.0f}%</b>" if offer.get("discount_percent") else ""
    verdict   = offer.get("deal_verdict") or ""
    verdict_emoji = _verdict_emoji(verdict)

    features = offer.get("key_features") or []
    feat_str = " · ".join(features[:3]) if features else ""

    lines = [
        f"{prefix}<a href=\"{url}\"><b>{title[:60]}</b></a>",
        f"💰 {price_str}{orig_str}{disc_str}  |  🏪 {store}",
    ]
    if verdict:
        lines.append(f"{verdict_emoji} {verdict}")
    if feat_str:
        lines.append(f"📋 {feat_str}")

    return "\n".join(lines)


def offers_list_html(offers: list[dict], header: str = "") -> str:
    """Render a numbered list of offer cards separated by dividers."""
    cards = [offer_card_html(o, i) for i, o in enumerate(offers, 1)]
    body  = "\n\n─────────────────\n\n".join(cards)
    return (f"<b>{_esc(header)}</b>\n\n" + body) if header else body


def comparison_table_html(offers: list[dict]) -> str:
    """Simple comparison text for Telegram (no Markdown tables in HTML mode)."""
    lines = ["<b>🔍 Angebotsvergleich</b>\n"]
    for i, o in enumerate(offers, 1):
        price = f"€{o['price']:.2f}" if o.get("price") else "?"
        disc  = f"-{o['discount_percent']:.0f}%" if o.get("discount_percent") else "–"
        lines.append(
            f"<b>{i}. {_esc(o.get('title','?')[:50])}</b>\n"
            f"   💰 {price} ({disc}) | 🏪 {_esc(o.get('store','?'))} | "
            f"{_verdict_emoji(o.get('deal_verdict',''))} {o.get('deal_verdict','?')}\n"
            f"   🔗 <a href=\"{o.get('url','')}\">Details</a>"
        )
    return "\n\n".join(lines)


def digest_html(sections: list[tuple[str, list[dict]]]) -> str:
    """
    Build a weekly digest HTML message.
    sections: list of (alert_name, offers_list)
    """
    parts = ["🛍️ <b>Dein wöchentlicher Angebots-Digest</b>\n"]
    for alert_name, offers in sections:
        parts.append(f"\n📌 <b>{_esc(alert_name)}</b>")
        for i, o in enumerate(offers[:5], 1):
            parts.append(offer_card_html(o, i))
        parts.append("─" * 20)
    return "\n".join(parts)


def _verdict_emoji(verdict: str) -> str:
    return {
        "Sehr gut":       "🌟",
        "Gut":            "✅",
        "Durchschnittlich": "➕",
        "Schlecht":       "⚠️",
    }.get(verdict, "")


def _esc(text: str) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
