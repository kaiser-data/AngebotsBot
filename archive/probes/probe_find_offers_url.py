"""Find the real URL pattern for kaufda offer-listing pages.

Strategy: visit homepage, dismiss cookies, collect all anchors and look for
patterns containing 'Angebote' or 'offer' or known retailers, then visit the
most promising one and check whether it actually renders offer cards (with
% discount + price text).
"""

import asyncio
import re
from collections import Counter

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 1000},
            locale="de-DE",
        )
        page = await context.new_page()
        await page.goto("https://www.kaufda.de", wait_until="networkidle", timeout=45_000)

        # cookie banner
        for sel in (
            "#onetrust-accept-btn-handler",
            "button:has-text('Akzeptieren')",
            "button:has-text('Alle akzeptieren')",
        ):
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(800)
                    break
            except Exception:
                pass

        anchors = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
        )
        print(f"Total anchors: {len(anchors)}")

        # Classify URL patterns
        paths = [re.sub(r"https?://[^/]+", "", a).split("?")[0] for a in anchors]
        path_prefixes = Counter()
        for p in paths:
            parts = p.strip("/").split("/")
            if parts:
                path_prefixes[parts[0]] += 1
        print("\nTop path prefixes:")
        for k, v in path_prefixes.most_common(15):
            print(f"  /{k}: {v}")

        # Look for candidate offer-listing URLs
        offer_like = sorted({
            a for a in anchors
            if any(kw in a for kw in ("Angebote", "angebote", "Aktuelle", "aktuelle-Angebote", "Offer"))
        })
        print(f"\nOffer-like anchors ({len(offer_like)}):")
        for a in offer_like[:30]:
            print(f"  {a}")

        # Look for retailer landing pages with offer listings
        retailer_links = sorted({
            a for a in anchors if "/Geschaefte/" in a
        })[:10]
        print(f"\nRetailer Geschaefte links ({len(retailer_links)}):")
        for a in retailer_links:
            print(f"  {a}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
