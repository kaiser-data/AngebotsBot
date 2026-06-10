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
        # Gemini 2.5 is a thinking model: its (invisible) reasoning tokens
        # count against max_tokens. At 4096 the visible completion was cut
        # off after a few hundred characters, which broke every JSON batch
        # response in the categorizer. 16k leaves room for both.
        max_tokens=16384,
    )
