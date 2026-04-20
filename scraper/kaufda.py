"""Playwright-based scraper for kaufda.de."""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from urllib.request import urlopen

from playwright.async_api import async_playwright, Page, BrowserContext
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config
from scraper.models import RawOffer
from scraper.utils import fingerprint_url, canonical_url, clean_price, clean_discount, jitter_sleep
from providers.supabase_client import get_supabase

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kaufda.de"

# Categories to scrape — update slugs if kaufda changes their navigation
CATEGORIES = [
    "elektronik",
    "haushalt",
    "mode",
    "sport-freizeit",
    "garten",
    "auto-motorrad",
    "gesundheit-beauty",
    "kinder-baby",
]


class KaufdaScraper:
    """Async Playwright scraper for kaufda.de deals."""

    def __init__(self):
        self._disallowed: list[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    async def scrape_new_offers(
        self,
        max_pages: int = config.KAUFDA_MAX_PAGES_PER_CATEGORY,
        max_offers: int = config.KAUFDA_MAX_OFFERS_PER_RUN,
    ) -> tuple[list[dict], list[str]]:
        """
        Scrape kaufda.de and return only offers not yet in the database.

        Returns:
            (new_offers_as_state_dicts, error_messages)
        """
        await self._load_robots_txt()

        all_offers: list[RawOffer] = []
        errors: list[str] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="de-DE",
            )

            # Scrape homepage + category pages
            pages_to_scrape = [BASE_URL] + [
                f"{BASE_URL}/kategorie/{slug}"
                for slug in CATEGORIES
                if not self._is_disallowed(f"/kategorie/{slug}")
            ]

            for page_url in pages_to_scrape:
                if len(all_offers) >= max_offers:
                    break
                try:
                    page_offers = await self._scrape_listing_page(
                        context, page_url, max_pages, category=self._slug_from_url(page_url)
                    )
                    all_offers.extend(page_offers)
                    logger.info("Scraped %d offers from %s", len(page_offers), page_url)
                except Exception as exc:
                    msg = f"Error scraping {page_url}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)

            await browser.close()

        # Dedup against database
        new_offers = await self._filter_new(all_offers[:max_offers])
        logger.info("Found %d new offers (total scraped: %d)", len(new_offers), len(all_offers))
        return [o.to_state_dict() for o in new_offers], errors

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _scrape_listing_page(
        self,
        context: BrowserContext,
        start_url: str,
        max_pages: int,
        category: Optional[str],
    ) -> list[RawOffer]:
        """Scrape up to max_pages of a listing page and return RawOffer list."""
        offers: list[RawOffer] = []
        current_url = start_url

        for page_num in range(max_pages):
            page = await context.new_page()
            try:
                await page.goto(current_url, wait_until="networkidle", timeout=30_000)
                page_offers = await self._extract_offers_from_page(page, category)
                offers.extend(page_offers)

                # Try to find the "next page" link
                next_url = await self._get_next_page_url(page, current_url)
                await page.close()

                if not next_url or page_num + 1 >= max_pages:
                    break

                current_url = next_url
                await jitter_sleep()

            except Exception as exc:
                await page.close()
                logger.warning("Page error on %s (page %d): %s", current_url, page_num, exc)
                break

        return offers

    async def _extract_offers_from_page(
        self, page: Page, category: Optional[str]
    ) -> list[RawOffer]:
        """Extract all offer cards from the current DOM state."""
        offers: list[RawOffer] = []

        # kaufda.de renders offer cards — these selectors target the common card pattern.
        # Adjust if kaufda updates their markup.
        card_selector = "article, [class*='offer'], [class*='deal'], [class*='product-card']"
        cards = await page.query_selector_all(card_selector)

        for card in cards:
            try:
                offer = await self._parse_card(card, page.url, category)
                if offer:
                    offers.append(offer)
            except Exception as exc:
                logger.debug("Card parse error: %s", exc)

        return offers

    async def _parse_card(self, card, page_url: str, category: Optional[str]) -> Optional[RawOffer]:
        """Extract offer fields from a single card element."""
        # Title
        title_el = await card.query_selector("h2, h3, [class*='title'], [class*='name']")
        title = (await title_el.inner_text()).strip() if title_el else None
        if not title or len(title) < 3:
            return None

        # URL
        link_el = await card.query_selector("a[href]")
        if not link_el:
            return None
        href = await link_el.get_attribute("href")
        url = canonical_url(BASE_URL, href)

        # Image
        img_el = await card.query_selector("img[src], img[data-src]")
        image_url = None
        if img_el:
            image_url = (
                await img_el.get_attribute("src")
                or await img_el.get_attribute("data-src")
            )
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

        # Price
        price_el = await card.query_selector("[class*='price-current'], [class*='current-price'], [class*='price']")
        price = clean_price(await price_el.inner_text() if price_el else None)

        # Original price
        orig_el = await card.query_selector("[class*='price-old'], [class*='original-price'], [class*='was'], del, s")
        original_price = clean_price(await orig_el.inner_text() if orig_el else None)

        # Discount badge
        disc_el = await card.query_selector("[class*='discount'], [class*='badge'], [class*='saving']")
        discount_raw = await disc_el.inner_text() if disc_el else None
        discount_percent = clean_discount(discount_raw)

        # Compute discount from prices if badge not found
        if discount_percent is None and price and original_price and original_price > 0:
            discount_percent = round((1 - price / original_price) * 100, 1)

        # Store
        store_el = await card.query_selector("[class*='store'], [class*='shop'], [class*='retailer'], [class*='brand']")
        store = (await store_el.inner_text()).strip() if store_el else None

        return RawOffer(
            external_id=fingerprint_url(url),
            title=title,
            url=url,
            image_url=image_url,
            price=price,
            original_price=original_price,
            discount_percent=discount_percent,
            store=store,
            category=category,
            scraped_at=datetime.utcnow(),
        )

    async def _get_next_page_url(self, page: Page, current_url: str) -> Optional[str]:
        """Find the 'next page' link on a listing page."""
        next_el = await page.query_selector(
            "a[rel='next'], a[aria-label*='nächste'], a[class*='next'], a[class*='pagination-next']"
        )
        if not next_el:
            return None
        href = await next_el.get_attribute("href")
        if not href:
            return None
        return canonical_url(BASE_URL, href)

    async def _filter_new(self, offers: list[RawOffer]) -> list[RawOffer]:
        """Remove offers whose external_id is already in the database."""
        if not offers:
            return []

        known_ids: set[str] = set()
        try:
            ids = [o.external_id for o in offers]
            # Query in chunks of 100
            for i in range(0, len(ids), 100):
                chunk = ids[i : i + 100]
                result = (
                    get_supabase()
                    .table("offers")
                    .select("external_id")
                    .in_("external_id", chunk)
                    .execute()
                )
                for row in (result.data or []):
                    known_ids.add(row["external_id"])
        except Exception as exc:
            logger.warning("Dedup query failed (including all offers): %s", exc)
            return offers

        return [o for o in offers if o.external_id not in known_ids]

    async def _load_robots_txt(self) -> None:
        """Read kaufda.de/robots.txt and store disallowed paths."""
        try:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None, lambda: urlopen(f"{BASE_URL}/robots.txt", timeout=5).read().decode()
            )
            for line in content.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path:
                        self._disallowed.append(path)
        except Exception as exc:
            logger.warning("Could not fetch robots.txt: %s", exc)

    def _is_disallowed(self, path: str) -> bool:
        return any(path.startswith(d) for d in self._disallowed if d and d != "/")

    @staticmethod
    def _slug_from_url(url: str) -> Optional[str]:
        """Extract category slug from a kaufda URL."""
        parts = url.rstrip("/").split("/")
        return parts[-1] if len(parts) > 3 else None
