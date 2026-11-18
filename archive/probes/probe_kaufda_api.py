"""Probe kaufda content-viewer-be API for structured offer data.

Hypotheses to test:
  1. /v1/brochures/{id} returns offers inline
  2. There's an /v1/brochures/{id}/offers endpoint
  3. /v1/offers?... search endpoint exists
  4. kaufda.de/Angebote pages expose structured offer JSON
"""

import asyncio
import json

import httpx

BROCHURE_ID = "897c4e41-7053-4691-b0a4-105b9b97a688"  # Lidl
BASE = "https://content-viewer-be.kaufda.de/v1"
COMMON = {"partner": "kaufda_web", "brochureKey": "", "lat": "52.522", "lng": "13.4161"}

CANDIDATES = [
    f"{BASE}/brochures/{BROCHURE_ID}",
    f"{BASE}/brochures/{BROCHURE_ID}/offers",
    f"{BASE}/brochures/{BROCHURE_ID}/items",
    f"{BASE}/brochures/{BROCHURE_ID}/products",
    f"{BASE}/brochures/{BROCHURE_ID}/hotspots",
    f"{BASE}/brochures/{BROCHURE_ID}/pages",
    f"{BASE}/offers?brochureId={BROCHURE_ID}",
    f"{BASE}/offers?retailer=Lidl&lat=52.522&lng=13.4161",
    "https://www.kaufda.de/api/v1/offers?retailer=Lidl",
    "https://www.kaufda.de/api/offers?retailer=Lidl",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
    "Origin": "https://www.kaufda.de",
    "Referer": "https://www.kaufda.de/",
}


async def main() -> None:
    async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as cli:
        for url in CANDIDATES:
            sep = "&" if "?" in url else "?"
            full = url + sep + "&".join(f"{k}={v}" for k, v in COMMON.items()) if "content-viewer-be" in url else url
            try:
                r = await cli.get(full)
            except Exception as e:
                print(f"[ERR] {full} -> {e}")
                continue
            ct = r.headers.get("content-type", "")
            print(f"\n[{r.status_code}] {ct}  {full[:120]}")
            if "application/json" in ct and r.status_code < 400:
                try:
                    data = r.json()
                except Exception:
                    print("   (json parse failed)", r.text[:200])
                    continue
                # Look for offer-shaped keys
                s = json.dumps(data) if not isinstance(data, str) else data
                hits = sorted(set(
                    k for k in ("offers", "products", "items", "hotspots", "price", "discount", "title")
                    if f'"{k}"' in s
                ))
                print(f"   keys hint: {hits}")
                if isinstance(data, dict):
                    print(f"   top-level: {list(data.keys())[:12]}")
                    if "content" in data and isinstance(data["content"], dict):
                        print(f"   content keys: {list(data['content'].keys())[:20]}")
                print(f"   sample: {s[:500]}")
            else:
                print(f"   body[:200]: {r.text[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
