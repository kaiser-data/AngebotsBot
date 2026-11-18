"""Load canonical taxonomy from dashboard/src/lib/taxonomy.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[1] / "dashboard" / "src" / "lib" / "taxonomy.json"
)


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    with _TAXONOMY_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    buckets = list(data["buckets"])
    subs = {k: list(v) for k, v in data["subcategories"].items()}
    fallbacks = dict(data.get("fallback_subcategory") or {})
    if set(buckets) != set(subs):
        missing = set(buckets) ^ set(subs)
        raise ValueError(f"taxonomy.json buckets/subcategories mismatch: {missing}")
    return {
        "buckets": buckets,
        "subcategories": subs,
        "fallback_subcategory": fallbacks,
    }


def taxonomy_buckets() -> list[str]:
    return list(load_taxonomy()["buckets"])


def taxonomy_subcategories() -> dict[str, list[str]]:
    return {k: list(v) for k, v in load_taxonomy()["subcategories"].items()}


def taxonomy_fallback(bucket: str) -> str:
    return load_taxonomy()["fallback_subcategory"].get(bucket, "Sonstige")
