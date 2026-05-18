"""Fast offer scraper that reads kaufda.de's own pre-extracted offer JSON.

Why: kaufda already extracts product, price, brand, validity, image, brochure
location, etc. for every offer and serves it inline in the page's
__NEXT_DATA__ blob on /Angebote/<keyword>. No Playwright, no vision model.

Flow:
  1. /Angebote-Uebersicht/<A-Z> → list of product keywords
  2. /Angebote/<keyword>        → __NEXT_DATA__.pageInformation.offers.main.items
  3. Map each item → RawOffer
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import string
from datetime import UTC, datetime
from typing import Optional

import httpx

import config
from scraper.models import RawOffer
from scraper.utils import fingerprint_url

logger = logging.getLogger(__name__)

BASE = "https://www.kaufda.de"
UEBERSICHT_LETTERS = list(string.ascii_uppercase)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}

LOYALTY_HINT_PATTERNS = (
    ("lidl_plus", ("lidl plus", "lidl+")),
    ("rewe_app", ("rewe app",)),
    ("edeka_app", ("edeka app",)),
    ("penny_app", ("penny app",)),
    ("payback", ("payback",)),
    ("app", ("nur mit app", "app-preis", "app preis", "mit app")),
    ("card", ("kundenkarte", "clubkarte", "treuekarte")),
)


def _parse_next_data(html: str) -> Optional[dict]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _to_iso(maybe_dt: Optional[str]) -> Optional[str]:
    """Pass through ISO date strings, normalising the timezone suffix."""
    if not maybe_dt:
        return None
    return maybe_dt.replace("+0000", "+00:00")


def _is_upcoming(valid_from_iso: Optional[str]) -> bool:
    if not valid_from_iso:
        return False
    try:
        dt = datetime.fromisoformat(valid_from_iso)
    except ValueError:
        return False
    return dt > datetime.now(UTC)


def _classify_loyalty(conditions: list[dict]) -> tuple[bool, Optional[str], Optional[str]]:
    """Return (requires_loyalty, program_name, free_text)."""
    free_text_parts: list[str] = []
    program: Optional[str] = None
    requires = False
    for cond in conditions or []:
        if not isinstance(cond, dict) or not cond:
            continue
        loyalty = cond.get("loyaltyProgram")
        if isinstance(loyalty, dict) and loyalty.get("isCard"):
            requires = True
            program = loyalty.get("name") or program
        other = cond.get("other")
        if isinstance(other, str) and other.strip():
            free_text_parts.append(other.strip())

    blob = " ".join(free_text_parts).lower()
    if not program:
        for tag, hints in LOYALTY_HINT_PATTERNS:
            if any(h in blob for h in hints):
                program = tag
                requires = True
                break

    return requires, program, " · ".join(free_text_parts) or None


def _build_viewer_url(brochure_id: str, page_number: Optional[int]) -> str:
    page = (page_number or 0) + 1  # kaufda uses 1-indexed viewer pages
    return (
        f"{BASE}/contentViewer/static/{brochure_id}"
        f"?feature=brochure_shelf&page={page}"
    )


def _compute_discount(main_price: Optional[float], secondary_price: Optional[float]) -> Optional[float]:
    if not main_price or not secondary_price:
        return None
    if secondary_price <= main_price:
        return None
    return round((secondary_price - main_price) / secondary_price * 100, 1)


def _item_to_raw_offer(item: dict, keyword: str) -> Optional[RawOffer]:
    try:
        offer_id = item.get("id")
        if not offer_id:
            return None

        parent = item.get("parentContent") or {}
        brochure_id = parent.get("id")
        page_no_zero = (parent.get("page") or {}).get("number")
        viewer_url = (
            _build_viewer_url(brochure_id, page_no_zero) if brochure_id else f"{BASE}/Angebote/{keyword}"
        )

        prices = item.get("prices") or {}
        main_price = prices.get("mainPrice") or None
        secondary_price = prices.get("secondaryPrice") or None
        if secondary_price == 0:
            secondary_price = None

        requires_loyalty, loyalty_program, cond_text = _classify_loyalty(
            prices.get("conditions") or []
        )

        # Whenever the strikethrough/UVP price is higher than the sale price,
        # treat secondary as the original price. Loyalty is a separate flag.
        original_price = secondary_price if (
            secondary_price and main_price and secondary_price > main_price
        ) else None
        loyalty_price = main_price if requires_loyalty else None
        standard_price = original_price or main_price

        discount = _compute_discount(main_price, secondary_price)

        valid_from = _to_iso(item.get("validFrom"))
        valid_to = _to_iso(item.get("validUntil"))

        images = (item.get("offerImages") or {}).get("url") or {}
        image_url = images.get("large") or images.get("normal") or images.get("thumbnail")

        title = item.get("title") or "(ohne Titel)"
        description = item.get("description") or ""
        brand = item.get("brand")
        if brand and brand.lower() not in title.lower():
            display_title = f"{brand} {title}"
        else:
            display_title = title

        return RawOffer(
            external_id=str(offer_id),
            title=display_title,
            url=viewer_url,
            image_url=image_url,
            price=main_price,
            standard_price=standard_price,
            loyalty_price=loyalty_price,
            original_price=original_price,
            discount_percent=discount,
            store=item.get("publisherName"),
            category=keyword,
            source_viewer_url=viewer_url,
            source_page_number=(page_no_zero + 1) if isinstance(page_no_zero, int) else None,
            source_page_image_url=None,
            requires_loyalty=requires_loyalty,
            loyalty_program=loyalty_program,
            price_condition_text=description or cond_text,
            validity_text=None,
            valid_from=valid_from,
            valid_to=valid_to,
            is_upcoming=_is_upcoming(valid_from),
        )
    except Exception as exc:
        logger.warning("Failed to map offer %s: %s", item.get("id"), exc)
        return None


# ── Public scraper class ────────────────────────────────────────────────────


class KaufdaJsonScraper:
    """Async scraper that mines kaufda's __NEXT_DATA__ for structured offers."""

    def __init__(
        self,
        *,
        concurrency: int = 8,
        request_timeout: float = 25.0,
        max_keywords: Optional[int] = None,
    ) -> None:
        self.concurrency = concurrency
        self.timeout = request_timeout
        self.max_keywords = max_keywords

    async def discover_keywords(self, client: httpx.AsyncClient) -> list[str]:
        """Fetch /Angebote-Uebersicht/<A-Z> and collect every product slug."""

        async def fetch_letter(letter: str) -> list[str]:
            url = f"{BASE}/Angebote-Uebersicht/{letter}"
            try:
                r = await client.get(url)
            except Exception as exc:
                logger.warning("Uebersicht %s failed: %s", letter, exc)
                return []
            if r.status_code != 200:
                logger.warning("Uebersicht %s status %s", letter, r.status_code)
                return []
            return re.findall(r'/Angebote/([A-Za-z0-9\-_%]+)', r.text)

        results = await asyncio.gather(*(fetch_letter(L) for L in UEBERSICHT_LETTERS))
        seen: set[str] = set()
        keywords: list[str] = []
        for batch in results:
            for kw in batch:
                if kw and kw not in seen:
                    seen.add(kw)
                    keywords.append(kw)
        logger.info("Discovered %d unique product keywords", len(keywords))
        return keywords

    async def fetch_keyword(
        self, client: httpx.AsyncClient, keyword: str
    ) -> list[RawOffer]:
        url = f"{BASE}/Angebote/{keyword}"
        try:
            r = await client.get(url)
        except Exception as exc:
            logger.warning("fetch %s failed: %s", keyword, exc)
            return []
        if r.status_code != 200:
            logger.debug("fetch %s -> %s", keyword, r.status_code)
            return []
        nd = _parse_next_data(r.text)
        if not nd:
            return []
        try:
            page_info = nd["props"]["pageProps"]["pageInformation"]
        except (KeyError, TypeError):
            return []
        offers_section = page_info.get("offers") or {}
        items: list[dict] = []
        for bucket_name in ("main", "topRanked", "otherPublishers"):
            bucket = offers_section.get(bucket_name)
            if isinstance(bucket, dict):
                items.extend(bucket.get("items") or [])
        raw_offers: list[RawOffer] = []
        for it in items:
            if it.get("type") != "OFFER":
                continue
            ro = _item_to_raw_offer(it, keyword)
            if ro:
                raw_offers.append(ro)
        return raw_offers

    async def scrape_all(self) -> tuple[list[dict], list[str]]:
        """Discover keywords then fetch all offers across them.

        Returns (list_of_state_dicts, error_messages).
        """
        errors: list[str] = []
        offers_by_id: dict[str, RawOffer] = {}

        limits = httpx.Limits(max_keepalive_connections=self.concurrency, max_connections=self.concurrency * 2)
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=self.timeout,
            limits=limits,
            follow_redirects=True,
            http2=False,
        ) as client:
            keywords = await self.discover_keywords(client)
            if self.max_keywords:
                keywords = keywords[: self.max_keywords]

            sem = asyncio.Semaphore(self.concurrency)

            async def worker(kw: str) -> None:
                async with sem:
                    try:
                        for ro in await self.fetch_keyword(client, kw):
                            offers_by_id.setdefault(ro.external_id, ro)
                    except Exception as exc:
                        errors.append(f"{kw}: {exc}")

            await asyncio.gather(*(worker(kw) for kw in keywords))

        unique_offers = list(offers_by_id.values())
        logger.info(
            "Scraped %d unique offers across %d keywords (%d errors)",
            len(unique_offers),
            len(keywords) if 'keywords' in locals() else 0,
            len(errors),
        )
        return [o.to_state_dict() for o in unique_offers], errors
