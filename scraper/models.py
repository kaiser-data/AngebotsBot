"""Pydantic models for raw scraped offer data."""

from datetime import UTC, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RawOffer(BaseModel):
    """A single offer as scraped from kaufda.de before any enrichment."""
    external_id: str
    title: str
    url: str
    image_url: Optional[str] = None
    price: Optional[float] = None
    standard_price: Optional[float] = None
    loyalty_price: Optional[float] = None
    original_price: Optional[float] = None
    discount_percent: Optional[float] = None
    store: Optional[str] = None
    category: Optional[str] = None
    source_viewer_url: Optional[str] = None
    source_page_number: Optional[int] = None
    source_page_image_url: Optional[str] = None
    requires_loyalty: bool = False
    loyalty_program: Optional[str] = None
    price_condition_text: Optional[str] = None
    validity_text: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_upcoming: bool = False
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("price", "original_price", "discount_percent", mode="before")
    @classmethod
    def clean_numeric(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.replace("€", "").replace(",", ".").replace("%", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                return None
        return float(v)

    def to_state_dict(self) -> dict:
        """Convert to the OfferData TypedDict shape used in AgentState."""
        return {
            "external_id":     self.external_id,
            "title":           self.title,
            "url":             self.url,
            "image_url":       self.image_url,
            "price":           self.price,
            "standard_price":  self.standard_price,
            "loyalty_price":   self.loyalty_price,
            "original_price":  self.original_price,
            "discount_percent": self.discount_percent,
            "store":           self.store,
            "category":        self.category,
            "source_viewer_url": self.source_viewer_url,
            "source_page_number": self.source_page_number,
            "source_page_image_url": self.source_page_image_url,
            "requires_loyalty": self.requires_loyalty,
            "loyalty_program": self.loyalty_program,
            "price_condition_text": self.price_condition_text,
            "validity_text":   self.validity_text,
            "valid_from":      self.valid_from,
            "valid_to":        self.valid_to,
            "is_upcoming":     self.is_upcoming,
            "scraped_at":      self.scraped_at.isoformat(),
        }
