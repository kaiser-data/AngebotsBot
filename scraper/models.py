"""Pydantic models for raw scraped offer data."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class RawOffer(BaseModel):
    """A single offer as scraped from kaufda.de before any enrichment."""
    external_id: str
    title: str
    url: str
    image_url: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    discount_percent: Optional[float] = None
    store: Optional[str] = None
    category: Optional[str] = None
    scraped_at: datetime = datetime.utcnow()

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
            "original_price":  self.original_price,
            "discount_percent": self.discount_percent,
            "store":           self.store,
            "category":        self.category,
            "scraped_at":      self.scraped_at.isoformat(),
        }
