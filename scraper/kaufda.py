"""Playwright-based scraper for kaufda.de."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Optional
from urllib.request import urlopen

from playwright.async_api import async_playwright, Page, BrowserContext
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config
from scraper.models import RawOffer
from scraper.utils import (
    fingerprint_url,
    canonical_url,
    clean_price,
    clean_discount,
    extract_loyalty_condition,
    jitter_sleep,
    parse_offer_validity,
    resolve_offer_prices,
)
from providers.supabase_client import get_supabase

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kaufda.de"
RETAILER_PAGES = {
    "lidl": f"{BASE_URL}/Geschaefte/Lidl",
    "edeka": f"{BASE_URL}/Geschaefte/Edeka",
    "aldi": f"{BASE_URL}/Geschaefte/Aldi-Nord",
    "aldi-nord": f"{BASE_URL}/Geschaefte/Aldi-Nord",
    "aldi-sued": f"{BASE_URL}/Geschaefte/Aldi-Sued",
}

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

    async def scrape_sample_offers(
        self,
        max_pages: int = 1,
        max_offers: int = 10,
    ) -> tuple[list[dict], list[str]]:
        """
        Scrape a small live sample from kaufda.de without database deduplication.

        This is used for human review flows where we want current catalog cards
        even if they already exist in Supabase.
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
                        context,
                        page_url,
                        max_pages,
                        category=self._slug_from_url(page_url),
                    )
                    all_offers.extend(page_offers)
                    logger.info("Scraped %d sample offers from %s", len(page_offers), page_url)
                except Exception as exc:
                    msg = f"Error scraping {page_url}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)

            await browser.close()

        sample_offers = all_offers[:max_offers]
        logger.info("Prepared %d sample offers for review", len(sample_offers))
        return [o.to_state_dict() for o in sample_offers], errors

    async def scrape_brochure_page_samples(
        self,
        retailers: list[str],
        pages_per_brochure: int = 2,
        max_items: int = 6,
    ) -> tuple[list[dict], list[str]]:
        """
        Scrape flyer-page images from retailer brochure viewers.

        This is intended for human review of multipage supermarket prospects.
        """
        errors: list[str] = []
        samples: list[dict] = []

        retailer_urls: list[tuple[str, str]] = []
        for retailer in retailers:
            url = RETAILER_PAGES.get(retailer)
            if url:
                retailer_urls.append((retailer, url))

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

            for retailer, retailer_url in retailer_urls:
                if len(samples) >= max_items:
                    break
                page = await context.new_page()
                try:
                    await page.goto(retailer_url, wait_until="networkidle", timeout=30_000)
                    await self._dismiss_overlays(page)

                    viewer = page.locator(".w-brochureViewer").first
                    if await viewer.count() == 0:
                        errors.append(f"No brochure viewer found for {retailer}")
                        await page.close()
                        continue

                    brochure_preview = page.locator("img[alt*='Aktueller']").first
                    brochure_title = await brochure_preview.get_attribute("alt") or f"{retailer.title()} Prospekt"
                    validity_text = await brochure_preview.get_attribute("title")

                    await viewer.click(force=True)
                    await page.wait_for_timeout(3_000)
                    await self._dismiss_overlays(page)

                    viewer_url = page.url
                    all_images = page.locator("img")
                    image_count = await all_images.count()
                    page_urls: list[str] = []
                    for idx in range(image_count):
                        src = await all_images.nth(idx).get_attribute("src")
                        if not src or "zoomlarge_page_" not in src:
                            continue
                        cleaned = src.split("?")[0]
                        if cleaned not in page_urls:
                            page_urls.append(cleaned)

                    for page_idx, image_url in enumerate(page_urls[:pages_per_brochure], start=1):
                        samples.append(
                            {
                                "external_id": fingerprint_url(f"{viewer_url}#page={page_idx}"),
                                "title": f"{retailer.title()} Prospekt Seite {page_idx}",
                                "url": f"{viewer_url.split('&page=')[0]}&page={page_idx}",
                                "image_url": image_url,
                                "price": None,
                                "original_price": None,
                                "discount_percent": None,
                                "store": retailer.title(),
                                "category": "prospekt",
                                "validity_text": validity_text,
                                "valid_from": None,
                                "valid_to": None,
                                "is_upcoming": False,
                                "scraped_at": datetime.now(UTC).isoformat(),
                                "brochure_title": brochure_title,
                                "page_number": page_idx,
                            }
                        )
                        if len(samples) >= max_items:
                            break

                except Exception as exc:
                    msg = f"Error scraping brochure pages for {retailer}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)
                finally:
                    await page.close()

            await browser.close()

        return samples[:max_items], errors

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
                await self._dismiss_overlays(page)
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
        image_cards = page.locator("img[title*='Angebot im aktuellen Prospekt']")
        card_count = await image_cards.count()

        for idx in range(card_count):
            try:
                offer = await self._parse_offer_card(page, image_cards.nth(idx), category)
                if offer:
                    offers.append(offer)
            except Exception as exc:
                logger.debug("Card parse error: %s", exc)

        return offers

    async def _parse_offer_card(self, page: Page, image_locator, category: Optional[str]) -> Optional[RawOffer]:
        """Extract one product-offer card from the current Kaufda layout."""
        card = image_locator.locator(
            "xpath=ancestor::div[contains(@class,'group') and contains(@class,'border-gray')][1]"
        )
        if await card.count() == 0:
            return None

        raw_card_text = await card.inner_text()
        if not raw_card_text:
            return None

        text_lines = [line.strip() for line in raw_card_text.splitlines() if line.strip()]
        if len(text_lines) < 3:
            return None
        card_text = " ".join(text_lines)

        image_url = await image_locator.get_attribute("src") or await image_locator.get_attribute("data-src")
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url

        brand = text_lines[0]
        store = text_lines[-2] if len(text_lines) >= 2 else None
        price = clean_price(text_lines[-1]) if text_lines else None
        title = " ".join(text_lines[1:-2]).strip() if len(text_lines) > 3 else (text_lines[1] if len(text_lines) > 1 else None)
        if not title:
            alt_text = await image_locator.get_attribute("alt")
            title = self._title_from_alt(alt_text)
        if not title or not price:
            return None

        detail_url, detail_text = await self._open_offer_detail(page, card)
        validity = parse_offer_validity(detail_text or card_text)
        loyalty = extract_loyalty_condition(detail_text or card_text)
        resolved_prices = resolve_offer_prices(
            price,
            detail_text or card_text,
            loyalty["requires_loyalty"],
        )

        original_price = self._extract_original_price(detail_text)
        discount_percent = None
        effective_price = resolved_prices["loyalty_price"] or resolved_prices["standard_price"] or price
        if effective_price and original_price and original_price > 0:
            discount_percent = round((1 - effective_price / original_price) * 100, 1)

        return RawOffer(
            external_id=fingerprint_url(detail_url),
            title=title,
            url=detail_url,
            image_url=image_url,
            price=resolved_prices["price"],
            standard_price=resolved_prices["standard_price"],
            loyalty_price=resolved_prices["loyalty_price"],
            original_price=original_price,
            discount_percent=discount_percent,
            store=store,
            category=category,
            requires_loyalty=loyalty["requires_loyalty"],
            loyalty_program=loyalty["loyalty_program"],
            price_condition_text=loyalty["price_condition_text"],
            validity_text=validity["validity_text"],
            valid_from=validity["valid_from"],
            valid_to=validity["valid_to"],
            is_upcoming=validity["is_upcoming"],
            scraped_at=datetime.now(UTC),
        )

    async def _open_offer_detail(self, page: Page, card) -> tuple[str, str]:
        """Open a product offer detail page, read its text, then go back."""
        start_url = page.url
        await self._dismiss_overlays(page)
        await card.click(timeout=10_000, force=True)
        await page.wait_for_timeout(3_000)
        detail_url = page.url
        detail_text = " ".join((await page.locator("body").inner_text()).split())
        if detail_url != start_url:
            await page.go_back(wait_until="domcontentloaded")
            await page.wait_for_timeout(2_000)
        return detail_url, detail_text

    @staticmethod
    def _title_from_alt(alt_text: str | None) -> Optional[str]:
        """Extract a product title from Kaufda image alt text."""
        if not alt_text:
            return None
        match = re.match(r"(.+?)\s+bei\s+.+?\s+im Prospekt", alt_text)
        if match:
            return match.group(1).strip()
        return alt_text.strip()

    @staticmethod
    def _extract_original_price(text: str | None) -> Optional[float]:
        """Best-effort extraction of an old price from detail text."""
        if not text:
            return None
        match = re.search(r"(?:statt|war)\s+(\d[\d\.,]*)\s*€", text, re.IGNORECASE)
        return clean_price(match.group(1)) if match else None

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

    async def _dismiss_overlays(self, page: Page) -> None:
        """Best-effort removal of consent overlays that block pointer events."""
        try:
            await page.evaluate(
                """
                () => {
                  const selectors = [
                    '#usercentrics-cmp-ui',
                    '[data-nosnippet="1"]#usercentrics-cmp-ui',
                    '[data-testid="uc-overlay"]',
                    '.uc-overlay',
                    '.uc-embedding-container',
                  ];
                  for (const selector of selectors) {
                    for (const el of document.querySelectorAll(selector)) {
                      el.remove();
                    }
                  }
                  document.documentElement.style.overflow = 'auto';
                  document.body.style.overflow = 'auto';
                }
                """
            )
        except Exception:
            pass

    @staticmethod
    def _slug_from_url(url: str) -> Optional[str]:
        """Extract category slug from a kaufda URL."""
        parts = url.rstrip("/").split("/")
        return parts[-1] if len(parts) > 3 else None
