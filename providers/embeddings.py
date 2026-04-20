"""
Embedding provider — ruft die Supabase generate-embedding Edge Function auf.

Kein PyTorch, keine lokalen Modelle. Die Edge Function nutzt gte-small (384-dim)
nativ in Deno, ohne externe API.
"""

import logging
from typing import Optional

import config
from providers.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def embed_text(text: str) -> list[float]:
    """
    Embed a single string by calling the Supabase generate-embedding Edge Function.
    Returns a 384-dimensional float vector.
    """
    if not text or not text.strip():
        return [0.0] * 384  # zero vector as safe fallback

    try:
        import json as _json
        sb = get_supabase()
        result = sb.functions.invoke(
            "generate-embedding",
            invoke_options={"body": {"text": text.strip()}},
        )
        # supabase-py returns bytes from functions.invoke
        if isinstance(result, (bytes, bytearray)):
            result = _json.loads(result)
        embedding = result.get("embedding") if isinstance(result, dict) else None
        if embedding and len(embedding) == 384:
            return embedding
        logger.error("Unexpected embedding response: %s", result)
    except Exception as exc:
        logger.error("embed_text failed: %s", exc)

    return [0.0] * 384


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple strings. Calls embed_text sequentially.
    (DB triggers handle offer/alert embeddings automatically — this is only
    used for search queries where we need the vector immediately.)
    """
    return [embed_text(t) for t in texts]
