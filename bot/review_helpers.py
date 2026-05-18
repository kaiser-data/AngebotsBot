"""Pure helpers for the Chainlit brochure-review flow.

Kept separate from app.py so they can be imported and tested without
loading Chainlit's UI runtime.
"""

import json
import re


DEFAULT_REVIEW_STORES = ("lidl", "aldi", "edeka")


def _is_review_request(text: str) -> bool:
    if "/review" in text:
        return True

    has_catalog_word = any(
        word in text
        for word in ("katalog", "kataloge", "catalog", "catalogs", "catalogue")
    )
    if not has_catalog_word:
        return False

    return any(word in text for word in ("review", "reviewv", "prüf", "pruef"))


def _extract_review_store_filters(text: str) -> list[str]:
    detected = [store for store in DEFAULT_REVIEW_STORES if store in text]
    return detected or list(DEFAULT_REVIEW_STORES)


def _extract_review_mode(text: str) -> str:
    if "manual" in text or "manuell" in text:
        return "manual"
    return "auto"


def _extract_json_object(raw: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _format_review_card_content(
    offer: dict,
    analysis: dict,
    position: int,
    total: int,
) -> str:
    scraped_title = offer.get("title") or "?"
    vision_title = analysis.get("product_name") or "?"
    features = analysis.get("key_features") or []
    feature_line = ", ".join(features[:4]) if features else "–"
    verdict = analysis.get("deal_verdict") or "?"
    brand = analysis.get("brand") or "?"
    condition = analysis.get("condition") or "?"
    validity = offer.get("validity_text") or "–"
    brochure_title = offer.get("brochure_title")
    page_number = offer.get("page_number")
    is_brochure_page = offer.get("category") == "prospekt"

    if is_brochure_page:
        top_offers = analysis.get("top_offers") or []
        offers_block = "\n".join(
            f"- {item.get('product', '?')} | {item.get('price', '?')} | {item.get('badge', '')}".rstrip(" |")
            for item in top_offers[:5]
        ) or "- Keine automatische Erkennung"
        page_summary = analysis.get("page_summary") or "Keine automatische Zusammenfassung"
        comparison_hint = analysis.get("comparison_hint") or "Manuelle Sichtprüfung nutzen"
        return (
            f"**Review {position}/{total}**\n\n"
            f"**Prospekt**\n"
            f"- Händler: {offer.get('store') or '?'}\n"
            f"- Titel: {brochure_title or offer.get('title') or '?'}\n"
            f"- Seite: {page_number or '?'}\n"
            f"- Gültigkeit: {validity}\n\n"
            f"**Automatische Erkennung**\n"
            f"- Zusammenfassung: {page_summary}\n"
            f"- Vergleichshinweis: {comparison_hint}\n"
            f"- Erkannte Angebote:\n{offers_block}\n\n"
            f"**Manuelle Prüfung**\n"
            f"- Prüfe, ob die sichtbaren Angebote und Preise zur Seite passen.\n"
            f"- Nutze Approve/Reject/Flag oder Edit.\n\n"
            f"**Quelle**\n"
            f"- URL: {offer.get('url') or '?'}"
        )

    return (
        f"**Review {position}/{total}**\n\n"
        f"**Scraped**\n"
        f"- Titel: {scraped_title}\n"
        f"- Shop: {offer.get('store') or '?'}\n"
        f"- Preis: {offer.get('price') or '?'}\n"
        f"- Gültigkeit: {validity}\n\n"
        f"**Vision**\n"
        f"- Produktname: {vision_title}\n"
        f"- Marke: {brand}\n"
        f"- Zustand: {condition}\n"
        f"- Urteil: {verdict}\n"
        f"- Features: {feature_line}\n\n"
        f"**Vergleich**\n"
        f"- Scraped vs Vision: `{scraped_title}` vs `{vision_title}`\n"
        f"- URL: {offer.get('url') or '?'}"
    )
