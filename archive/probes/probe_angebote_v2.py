"""Deeper probe of /Angebote pages — wait longer, scroll, sniff XHR, dump DOM.

The user says these pages always show "maximum discount" per offer. So there
must be structured offer cards. Goal: identify the JSON endpoint OR DOM
selectors that yield {title, image, discount, price, store, validity}.
"""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


URL = "https://www.kaufda.de/Angebote/Lidl"


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

        json_xhr: list[tuple[str, int, str]] = []

        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            if "application/json" not in ct:
                return
            u = resp.url
            if "tk.kaufda" in u or "nr-data" in u or "/sessionData" in u or "/account/id" in u:
                return
            try:
                body = await resp.text()
            except Exception:
                return
            json_xhr.append((u, resp.status, body))

        page = await context.new_page()
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        await page.goto(URL, wait_until="domcontentloaded", timeout=45_000)

        # Cookie banner
        for sel in (
            "#onetrust-accept-btn-handler",
            "button:has-text('Akzeptieren')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Accept')",
        ):
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(800)
                    break
            except Exception:
                pass

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await page.wait_for_timeout(2000)

        # Scroll to trigger lazy-loaded XHRs
        for _ in range(6):
            await page.mouse.wheel(0, 1600)
            await page.wait_for_timeout(700)

        await page.wait_for_timeout(1500)

        # Look for offer-card-ish elements
        print("\n== DOM selector counts ==")
        for sel in [
            "[data-testid]",
            "article",
            "[role='listitem']",
            "[class*='Card']",
            "[class*='card']",
            "[class*='Offer']",
            "[class*='offer']",
            "[class*='Tile']",
            "[class*='tile']",
            "a[href*='/Angebote/']",
            "img[alt][src*='bonial']",
        ]:
            try:
                c = await page.locator(sel).count()
            except Exception:
                c = -1
            print(f"  {sel:40s} {c}")

        # Print 5 unique data-testid values seen
        testids = await page.evaluate(
            "() => Array.from(new Set([...document.querySelectorAll('[data-testid]')]"
            ".map(e => e.getAttribute('data-testid')))).slice(0, 40)"
        )
        print("\nUnique data-testids:", testids)

        # Capture the page title + visible text snippet
        title = await page.title()
        print(f"\ndocument.title: {title}")

        # Search visible text for "%" (discount indicators)
        percent_count = await page.evaluate(
            "() => (document.body.innerText.match(/%/g) || []).length"
        )
        print(f"Visible '%' occurrences: {percent_count}")

        # Dump full HTML for offline inspection
        html = await page.content()
        out = Path("/tmp/kaufda_angebote_lidl.html")
        out.write_text(html)
        print(f"HTML dumped: {out} ({len(html)} bytes)")

        # Filter XHR responses to interesting ones
        print(f"\n== Captured {len(json_xhr)} json XHR ==")
        for u, status, body in json_xhr:
            print(f"\n[{status}] {u[:140]}")
            print(f"   {body[:300]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
