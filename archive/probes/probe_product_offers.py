"""Inspect a real kaufda /Angebote/<product> page for structured offer cards."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


URL = "https://www.kaufda.de/Angebote/Ariel"


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
            if any(skip in u for skip in ("tk.kaufda", "nr-data", "/sessionData", "/account/id", "usercentrics", "cmp")):
                return
            try:
                body = await resp.text()
            except Exception:
                return
            json_xhr.append((u, resp.status, body))

        page = await context.new_page()
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        await page.goto(URL, wait_until="domcontentloaded", timeout=45_000)

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

        await page.wait_for_load_state("networkidle", timeout=20_000)
        await page.wait_for_timeout(1500)

        for _ in range(5):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(600)

        print(f"document.title: {await page.title()}")
        body_text = await page.evaluate("() => document.body.innerText")
        print(f"body text length: {len(body_text)}")
        # show first 400 chars
        print(f"\n--- body[:600] ---\n{body_text[:600]}\n--- end ---\n")
        pct = body_text.count("%")
        eur = body_text.count("€")
        print(f"'%' = {pct}, '€' = {eur}")

        # Try lots of selectors
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
            "[class*='Product']",
            "[class*='product']",
            "a[href*='/contentViewer/']",
            "img[src*='bonial']",
            "img[src*='kaufda']",
        ]:
            try:
                c = await page.locator(sel).count()
            except Exception:
                c = -1
            if c:
                print(f"  {sel:40s} {c}")

        testids = await page.evaluate(
            "() => Array.from(new Set([...document.querySelectorAll('[data-testid]')]"
            ".map(e => e.getAttribute('data-testid')))).slice(0, 40)"
        )
        print(f"\nUnique data-testids ({len(testids)}):", testids)

        # __NEXT_DATA__
        nd_text = await page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }"
        )
        if nd_text:
            print(f"\n__NEXT_DATA__ size: {len(nd_text)}")
            try:
                nd = json.loads(nd_text)
                Path("/tmp/kaufda_ariel_next_data.json").write_text(json.dumps(nd, ensure_ascii=False, indent=2))
                print("dumped to /tmp/kaufda_ariel_next_data.json")
                pp = nd.get("props", {}).get("pageProps", {})
                print("pageProps keys:", list(pp.keys()))
                for k, v in pp.items():
                    if isinstance(v, list):
                        print(f"  pp.{k} list[{len(v)}]; sample keys: {list(v[0].keys())[:10] if v and isinstance(v[0], dict) else '?'}")
                    elif isinstance(v, dict):
                        print(f"  pp.{k} dict keys: {list(v.keys())[:10]}")
            except Exception as e:
                print("parse err:", e)

        # Dump HTML
        html = await page.content()
        Path("/tmp/kaufda_ariel.html").write_text(html)
        print(f"\nHTML dumped: /tmp/kaufda_ariel.html ({len(html)} bytes)")

        # XHR
        print(f"\n== {len(json_xhr)} json XHR ==")
        for u, status, body in json_xhr:
            print(f"\n[{status}] {u[:140]}")
            print(f"  {body[:300]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
