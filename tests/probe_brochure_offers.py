"""Probe a kaufda brochure viewer for embedded structured offer data.

We open the Lidl viewer URL the user shared, wait for it to render, and look
for: (a) hotspot/offer markup in the DOM, (b) JSON-LD or window.__NEXT_DATA__
style hydration payloads, (c) network requests that might return offer JSON.
"""

import asyncio
import json
import re

from playwright.async_api import async_playwright

URL = (
    "https://www.kaufda.de/contentViewer/static/"
    "897c4e41-7053-4691-b0a4-105b9b97a688"
    "?adFormat=ad_format__brochure_card_cover"
    "&adPlacement=ad_placement__shelf_fixed_position_1"
    "&feature=brochure_shelf&lat=52.522&lng=13.4161"
    "&pageType=SHELF_PAGE&retailerName=Lidl&sourceValue=Lidl"
    "&sourceType=PORTAL_WIDGET&visitOriginType=WEB_REFERRER_SEO"
    "&zip=10178&page=1"
)


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 1000},
            locale="de-DE",
        )

        json_responses: list[tuple[str, int, str]] = []

        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            url = resp.url
            if "application/json" not in ct:
                return
            # Filter to likely-offer endpoints
            if not any(kw in url.lower() for kw in (
                "offer", "shelf", "brochure", "content", "product", "page"
            )):
                return
            try:
                body = await resp.text()
            except Exception:
                return
            json_responses.append((url, resp.status, body[:400]))

        page = await context.new_page()
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        await page.goto(URL, wait_until="networkidle", timeout=45_000)
        await page.wait_for_timeout(3000)

        # Dismiss cookie banner if present
        for selector in (
            "button:has-text('Akzeptieren')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Accept')",
            "#onetrust-accept-btn-handler",
        ):
            try:
                el = page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                pass

        # 1. JSON-LD
        ld_scripts = page.locator("script[type='application/ld+json']")
        n_ld = await ld_scripts.count()
        print(f"\n== JSON-LD scripts: {n_ld} ==")
        for i in range(n_ld):
            txt = await ld_scripts.nth(i).inner_text()
            print(f"--- ld[{i}] ({len(txt)} chars) ---")
            try:
                parsed = json.loads(txt)
                print(json.dumps(parsed, ensure_ascii=False, indent=2)[:800])
            except Exception:
                print(txt[:500])

        # 2. __NEXT_DATA__ / window.__INITIAL_STATE__
        print("\n== Hydration payloads ==")
        next_data = await page.evaluate(
            "() => {"
            "  const el = document.getElementById('__NEXT_DATA__');"
            "  return el ? el.textContent : null;"
            "}"
        )
        if next_data:
            print(f"__NEXT_DATA__ length: {len(next_data)}")
            try:
                nd = json.loads(next_data)
                # Try to find offer-shaped content
                s = json.dumps(nd)
                hits = re.findall(r'"(offers?|products?|items?|hotspots?)"\s*:', s)
                print(f"shape hints: {set(hits)}")
                # Print top-level keys for orientation
                if isinstance(nd, dict):
                    print("top keys:", list(nd.keys())[:10])
                    props = nd.get("props", {})
                    if isinstance(props, dict):
                        print("props.keys:", list(props.keys())[:10])
                        pp = props.get("pageProps", {})
                        if isinstance(pp, dict):
                            print("pageProps.keys:", list(pp.keys())[:20])
            except Exception as e:
                print("parse error:", e)
        else:
            print("no __NEXT_DATA__")

        # 3. DOM hotspot / offer elements
        print("\n== DOM offer markers ==")
        for sel in [
            "[data-testid*='offer']",
            "[class*='offer']",
            "[class*='Offer']",
            "[class*='hotspot']",
            "[class*='Hotspot']",
            "[data-offer]",
            "a[href*='offer']",
            "[data-track*='offer']",
        ]:
            try:
                c = await page.locator(sel).count()
            except Exception:
                c = -1
            if c:
                print(f"  {sel}: {c}")

        # 4. JSON network responses we captured
        print(f"\n== JSON responses captured: {len(json_responses)} ==")
        for url, status, snippet in json_responses[:15]:
            print(f"[{status}] {url}")
            print(f"   snippet: {snippet[:300]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
