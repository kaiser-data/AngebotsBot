"""Vision LLM provider — Gemini via OpenAI-compatible endpoint."""

from functools import lru_cache

from openai import AsyncOpenAI

import config


@lru_cache(maxsize=1)
def get_vision_client() -> AsyncOpenAI:
    """Return an async OpenAI client configured for Gemini vision model."""
    return AsyncOpenAI(
        api_key=config.GEMINI_API_KEY,
        base_url=config.GEMINI_BASE_URL,
    )


# System prompt (German) for structured offer extraction
VISION_SYSTEM_PROMPT = (
    "Du bist ein Produktanalyst für einen deutschen Preisvergleichsdienst. "
    "Analysiere das Produktbild und gib strukturierte Produktinformationen zurück. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt ohne weitere Erklärungen."
)

# User prompt template — fill with offer metadata alongside the image
VISION_USER_TEMPLATE = """\
Analysiere dieses Produktangebot:
Titel: {title}
Preis: {price} EUR (war: {original_price} EUR, -{discount}%)
Shop: {store}

Extrahiere folgende Informationen als JSON:
{{
  "product_name": "exakter Produktname laut Bild",
  "brand": "Markenname oder 'unbekannt'",
  "condition": "neu|gebraucht|refurbished|unbekannt",
  "key_features": ["Feature 1", "Feature 2"],
  "quality_score": 0.85,
  "deal_verdict": "Sehr gut|Gut|Durchschnittlich|Schlecht",
  "tags": ["elektronik", "laptop"]
}}

quality_score-Kriterien (0.0–1.0):
- 0.9-1.0: Außergewöhnliches Angebot (>40% Rabatt, bekannte Marke, Neuware)
- 0.7-0.9: Gutes Angebot
- 0.5-0.7: Durchschnittlich
- <0.5: Schlechtes Preis-Leistungs-Verhältnis"""
