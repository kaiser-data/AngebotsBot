"""Text LLM provider — Gemini OpenAI-compatible endpoint."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

import config


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """Return a ChatOpenAI instance pointing at Gemini."""
    return ChatOpenAI(
        model=config.TEXT_MODEL,
        openai_api_key=config.GEMINI_API_KEY,
        openai_api_base=config.GEMINI_BASE_URL,
        temperature=temperature,
        max_tokens=4096,
    )
