"""
Embedding provider — ruft die Supabase generate-embedding Edge Function auf.

Kein PyTorch, keine lokalen Modelle. Die Edge Function nutzt gte-small (384-dim)
nativ in Deno, ohne externe API.
"""

from __future__ import annotations

import logging
from typing import Any

import config
from providers.supabase_client import get_supabase

logger = logging.getLogger(__name__)

ZERO = [0.0] * 384
BATCH_CHUNK = 32


def _parse_invoke_result(result: Any) -> Any:
    if isinstance(result, (bytes, bytearray)):
        import json as _json
        return _json.loads(result)
    return result


def embed_text(text: str) -> list[float]:
    """
    Embed a single string by calling the Supabase generate-embedding Edge Function.
    Returns a 384-dimensional float vector.
    """
    if not text or not text.strip():
        return list(ZERO)

    vectors = embed_batch([text.strip()])
    return vectors[0] if vectors else list(ZERO)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple strings in one Edge Function invoke (chunked).

    Empty strings become zero vectors. On failure the whole chunk falls back
    to zero vectors so callers can keep writing without aborting a scrape.
    """
    if not texts:
        return []

    out: list[list[float]] = [list(ZERO) for _ in texts]
    non_empty_idx = [i for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty_idx:
        return out

    try:
        sb = get_supabase()
    except Exception as exc:
        logger.error("embed_batch: supabase unavailable: %s", exc)
        return out

    for start in range(0, len(non_empty_idx), BATCH_CHUNK):
        chunk_idx = non_empty_idx[start : start + BATCH_CHUNK]
        chunk_texts = [texts[i].strip() for i in chunk_idx]
        try:
            result = _parse_invoke_result(
                sb.functions.invoke(
                    "generate-embedding",
                    invoke_options={"body": {"texts": chunk_texts}},
                )
            )
            embeddings = None
            if isinstance(result, dict):
                embeddings = result.get("embeddings")
                if embeddings is None and result.get("embedding") is not None:
                    embeddings = [result["embedding"]]
            if not isinstance(embeddings, list) or len(embeddings) != len(chunk_texts):
                logger.error("Unexpected embed_batch response: %s", result)
                continue
            for i, emb in zip(chunk_idx, embeddings):
                if isinstance(emb, list) and len(emb) == 384:
                    out[i] = emb
                else:
                    logger.error("Bad embedding length for index %s", i)
        except Exception as exc:
            logger.error("embed_batch failed: %s", exc)

    return out


def drain_embedding_queue(limit: int = 200) -> int:
    """
    Process pending embedding_queue rows in batches.

    Returns the number of queue rows removed. Safe to call when the queue
    table / migration 011 is not applied yet (logs and returns 0).
    """
    sb = get_supabase()
    try:
        res = (
            sb.table("embedding_queue")
            .select("id,table_name,record_id,field,text")
            .order("id")
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        logger.warning("embedding_queue unavailable (%s) — skip drain", exc)
        return 0

    jobs: list[dict] = res.data or []
    if not jobs:
        return 0

    vectors = embed_batch([j.get("text") or "" for j in jobs])
    done_ids: list[int] = []

    for job, vec in zip(jobs, vectors):
        table = job.get("table_name")
        record_id = job.get("record_id")
        field = job.get("field") or "embedding"
        if not table or not record_id:
            done_ids.append(job["id"])
            continue
        if not vec or len(vec) != 384 or all(v == 0 for v in vec):
            logger.warning("Skipping zero/invalid embedding for queue id=%s", job["id"])
            done_ids.append(job["id"])
            continue
        try:
            sb.table(table).update({field: vec}).eq("id", record_id).execute()
            done_ids.append(job["id"])
        except Exception as exc:
            logger.error(
                "Failed to write embedding for %s/%s: %s", table, record_id, exc
            )

    if done_ids:
        try:
            sb.table("embedding_queue").delete().in_("id", done_ids).execute()
        except Exception as exc:
            logger.error("Failed to delete drained queue rows: %s", exc)

    logger.info("Drained %d/%d embedding_queue rows", len(done_ids), len(jobs))
    return len(done_ids)
