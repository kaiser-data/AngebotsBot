"""Scraper utilities: fingerprinting, dedup, rate limiting."""

import asyncio
import hashlib
import random
import re
from urllib.parse import urlparse, urljoin

import config


def fingerprint_url(url: str) -> str:
    """Return a 16-char SHA-1 hex digest of the canonical URL."""
    canonical = url.strip().rstrip("/").lower()
    return hashlib.sha1(canonical.encode()).hexdigest()[:16]


def canonical_url(base: str, href: str) -> str:
    """Resolve a potentially relative href against a base URL."""
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def clean_price(text: str | None) -> float | None:
    """Extract a float price from a German-formatted string like '1.299,99 €'."""
    if not text:
        return None
    text = text.replace(".", "").replace(",", ".").replace("€", "").strip()
    match = re.search(r"[\d]+\.?[\d]*", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def clean_discount(text: str | None) -> float | None:
    """Extract discount percentage from a string like '-38%'."""
    if not text:
        return None
    match = re.search(r"[\d]+\.?[\d]*", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


async def jitter_sleep() -> None:
    """Sleep a random interval to avoid rate-limiting."""
    delay = random.uniform(
        config.SCRAPER_INTER_PAGE_DELAY_MIN,
        config.SCRAPER_INTER_PAGE_DELAY_MAX,
    )
    await asyncio.sleep(delay)
