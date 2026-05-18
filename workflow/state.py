"""LangGraph shared state definitions."""

import operator
from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class OfferData(TypedDict):
    """Raw scraped offer data from kaufda.de."""
    external_id: str          # SHA-1 of URL (16 chars)
    title: str
    url: str
    image_url: Optional[str]
    price: Optional[float]
    standard_price: Optional[float]
    loyalty_price: Optional[float]
    original_price: Optional[float]
    discount_percent: Optional[float]
    store: Optional[str]
    category: Optional[str]
    source_viewer_url: Optional[str]
    source_page_number: Optional[int]
    source_page_image_url: Optional[str]
    requires_loyalty: bool
    loyalty_program: Optional[str]
    price_condition_text: Optional[str]
    validity_text: Optional[str]
    valid_from: Optional[str]
    valid_to: Optional[str]
    is_upcoming: bool
    scraped_at: str           # ISO timestamp


class AnalyzedOffer(TypedDict):
    """Structured output from Gemini vision analysis."""
    external_id: str          # matches OfferData.external_id
    product_name: str
    brand: str
    condition: str            # neu / gebraucht / refurbished / unbekannt
    key_features: list[str]
    quality_score: float      # 0.0–1.0
    deal_verdict: str         # Sehr gut / Gut / Durchschnittlich / Schlecht
    tags: list[str]
    raw_llm_response: str


IntentType = Literal[
    "scrape",
    "query",
    "compare",
    "set_alert",
    "list_alerts",
    "delete_alert",
    "unknown",
]


class AgentState(TypedDict):
    # ── Conversation ─────────────────────────────────────────────────────────
    # operator.add accumulates messages across nodes (never overwritten)
    messages: Annotated[list[BaseMessage], operator.add]
    user_query: str

    # ── Routing ──────────────────────────────────────────────────────────────
    intent: IntentType

    # ── Scraping ─────────────────────────────────────────────────────────────
    scrape_requested: bool
    scraped_offers: list[OfferData]
    scrape_errors: list[str]

    # ── Vision analysis ──────────────────────────────────────────────────────
    analyzed_offers: list[AnalyzedOffer]
    vision_errors: list[str]

    # ── Storage ──────────────────────────────────────────────────────────────
    offers_stored: list[str]   # offer IDs successfully upserted
    db_errors: list[str]

    # ── Query / RAG ──────────────────────────────────────────────────────────
    query_results: list[dict]
    comparison_result: str

    # ── Alerts ───────────────────────────────────────────────────────────────
    alert_config: Optional[dict]   # pending alert being set up / operated on
    active_alerts: list[dict]

    # ── Response ─────────────────────────────────────────────────────────────
    final_response: str

    # ── Guard ────────────────────────────────────────────────────────────────
    iteration_count: int
