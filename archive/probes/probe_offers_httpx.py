"""Confirm structured offers can be pulled via plain httpx — no Playwright."""

import asyncio
import json
import re

import httpx

URL = "https://www.kaufda.de/Angebote/Ariel"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}


async def main() -> None:
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as cli:
        r = await cli.get(URL)
        print(f"status={r.status_code}, len={len(r.text)}")
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text,
            re.DOTALL,
        )
        if not m:
            print("__NEXT_DATA__ not found")
            return
        nd = json.loads(m.group(1))
        pi = nd["props"]["pageProps"]["pageInformation"]
        items = pi["offers"]["main"]["items"]
        print(f"\nfound {len(items)} main offers\n")
        for it in items[:5]:
            print(json.dumps({
                "title": it.get("title"),
                "brand": it.get("brand"),
                "publisher": it.get("publisherName"),
                "price": it.get("prices", {}).get("mainPriceFormatted"),
                "valid": f'{it.get("validFrom")} → {it.get("validUntil")}',
                "image": it.get("offerImages", {}).get("url", {}).get("large"),
                "brochureId": it.get("parentContent", {}).get("id"),
                "page": it.get("parentContent", {}).get("page", {}).get("number"),
                "desc": (it.get("description") or "")[:80],
            }, ensure_ascii=False, indent=2))
            print()
        # Plus any "otherPublishers" / "topRanked"
        for bucket in ("otherPublishers", "topRanked"):
            bdata = pi["offers"].get(bucket)
            if bdata and isinstance(bdata, dict):
                bitems = bdata.get("items", [])
                print(f"{bucket}: {len(bitems)} items")


if __name__ == "__main__":
    asyncio.run(main())
