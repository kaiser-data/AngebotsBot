"""Open a brochure viewer and watch for per-page offer/hotspot XHR.

URL: the second link the user sent (newer Lidl brochure b7c6f8dd...).
Goal: find whether brochure-viewer fetches a per-page offer payload.
"""

import asyncio

from playwright.async_api import async_playwright


URL = (
    "https://www.kaufda.de/contentViewer/static/"
    "b7c6f8dd-bd2a-45bc-881c-0c5b138ca40f"
    "?adFormat=ad_format__brochure_card_cover"
    "&adPlacement=ad_placement__shelf_sort_managed"
    "&feature=brochure_shelf&lat=52.522&lng=13.4161"
    "&pageType=SHELF_PAGE&retailerName=Lidl&sourceValue=Lidl"
    "&sourceType=PORTAL_WIDGET&visitOriginType=WEB_REFERRER_SEO"
    "&zip=10178&page=1"
)

BROCHURE_ID = "b7c6f8dd-bd2a-45bc-881c-0c5b138ca40f"


async def main() -> None:
    json_xhr: list[tuple[str, int, str]] = []

    async def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "application/json" not in ct:
            return
        u = resp.url
        if any(skip in u for skip in (
            "tk.kaufda", "nr-data", "/sessionData", "/account/id",
            "usercentrics", "cmp", "google", "facebook"
        )):
            return
        try:
            body = await resp.text()
        except Exception:
            return
        json_xhr.append((u, resp.status, body))

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
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        await page.goto(URL, wait_until="networkidle", timeout=45_000)

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

        # Navigate through a few pages of the brochure to trigger any
        # per-page offer fetch.
        await page.wait_for_timeout(2000)

        # Try clicking on page area — many viewers reveal hotspot overlays on click.
        viewer = page.locator("canvas, .pageContainer, [class*='page']").first
        try:
            if await viewer.count() > 0:
                box = await viewer.bounding_box()
                if box:
                    # click center of viewer
                    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    await page.wait_for_timeout(1500)
        except Exception as e:
            print("viewer click err:", e)

        # next page key
        for _ in range(3):
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(1200)

        await page.wait_for_timeout(2000)

        # Direct API probes (try plausible paths)
        print("\n== Direct API probes ==")
        for path in [
            f"/v1/brochures/{BROCHURE_ID}/clippings",
            f"/v1/brochures/{BROCHURE_ID}/offers",
            f"/v1/brochures/{BROCHURE_ID}/pages/0/offers",
            f"/v1/brochures/{BROCHURE_ID}/pages/0/clippings",
            f"/v1/brochures/{BROCHURE_ID}/hotspots",
            f"/v1/offers?brochureId={BROCHURE_ID}&page=0",
        ]:
            url = f"https://content-viewer-be.kaufda.de{path}"
            sep = "&" if "?" in url else "?"
            full = f"{url}{sep}partner=kaufda_web&lat=52.522&lng=13.4161"
            r = await page.request.get(full, headers={"Accept": "application/json"})
            print(f"  [{r.status}] {full}")
            if r.status == 200:
                body = await r.text()
                print(f"     {body[:300]}")

        # Print captured json XHR for inspection
        print(f"\n== Captured XHR ({len(json_xhr)}) ==")
        for u, status, body in json_xhr:
            print(f"\n[{status}] {u[:140]}")
            print(f"   {body[:280]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
