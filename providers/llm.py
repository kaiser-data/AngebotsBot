"""Text LLM provider — Featherless OpenAI-compatible endpoint."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

import config


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """Return a ChatOpenAI instance pointing at Featherless."""
    return ChatOpenAI(
        model=config.TEXT_MODEL,
        openai_api_key=config.FEATHERLESS_API_KEY,
        openai_api_base=config.FEATHERLESS_BASE_URL,
        temperature=temperature,
        max_tokens=2048,
    )
