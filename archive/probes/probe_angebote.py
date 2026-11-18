"""Find structured offer data on kaufda.de/Angebote pages.

Tries:
  - kaufda.de/Angebote (main offer index)
  - kaufda.de/Angebote/Lidl
  - kaufda.de/Angebote/Edeka
Looks for: __NEXT_DATA__, JSON-LD, offer markup, network XHR JSON.
"""

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright


URLS = [
    "https://www.kaufda.de/Angebote",
    "https://www.kaufda.de/Angebote/Lidl",
    "https://www.kaufda.de/Angebote/Edeka",
]


async def inspect(page, url: str) -> None:
    print(f"\n###############\n# {url}\n###############")

    api_responses: list[tuple[str, int, str]] = []

    async def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "application/json" not in ct:
            return
        u = resp.url
        if not any(k in u for k in ("kaufda", "bonial")):
            return
        try:
            body = await resp.text()
        except Exception:
            return
        api_responses.append((u, resp.status, body))

    page.on("response", lambda r: asyncio.create_task(on_response(r)))

    await page.goto(url, wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(2500)

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
                await page.wait_for_timeout(500)
                break
        except Exception:
            pass

    # __NEXT_DATA__
    nd_text = await page.evaluate(
        "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }"
    )
    if nd_text:
        try:
            nd = json.loads(nd_text)
            print(f"__NEXT_DATA__ size: {len(nd_text)} bytes")
            top = nd.get("props", {}).get("pageProps", {})
            print("pageProps keys:", list(top.keys())[:30])
            for k, v in top.items():
                if isinstance(v, list):
                    print(f"  pageProps.{k} = list[{len(v)}]")
                    if v and isinstance(v[0], dict):
                        print(f"    item0 keys: {list(v[0].keys())[:15]}")
                elif isinstance(v, dict):
                    print(f"  pageProps.{k} keys: {list(v.keys())[:15]}")
            # Dump pageProps to disk for inspection
            outpath = Path(f"/tmp/next_data_{re.sub('[^a-zA-Z0-9]', '_', url)}.json")
            outpath.write_text(json.dumps(top, ensure_ascii=False, indent=2))
            print(f"  pageProps dumped to: {outpath}")
        except Exception as e:
            print("nd parse error:", e)
    else:
        print("no __NEXT_DATA__")

    # JSON-LD
    ld_count = await page.locator("script[type='application/ld+json']").count()
    print(f"JSON-LD scripts: {ld_count}")
    for i in range(ld_count):
        txt = await page.locator("script[type='application/ld+json']").nth(i).inner_text()
        try:
            parsed = json.loads(txt)
            t = parsed.get("@type") if isinstance(parsed, dict) else None
            print(f"  ld[{i}] @type={t}, len={len(txt)}")
        except Exception:
            pass

    # Offer DOM hints
    for sel in [
        "[data-testid*='offer']",
        "article[data-testid]",
        "[class*='offer']",
        "[class*='Offer']",
        "[data-track*='offer']",
    ]:
        try:
            c = await page.locator(sel).count()
        except Exception:
            c = -1
        if c:
            print(f"DOM {sel}: {c}")

    # First few JSON responses
    print(f"JSON XHR captured: {len(api_responses)}")
    for u, status, body in api_responses[:8]:
        print(f"  [{status}] {u[:120]}")
        print(f"     {body[:200]}")


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
        for url in URLS:
            page = await context.new_page()
            try:
                await inspect(page, url)
            except Exception as e:
                print(f"ERROR {url}: {e}")
            finally:
                await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
