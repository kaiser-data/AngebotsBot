"""Live fetch smoke-test for KaufdaScraper.scrape_brochure_page_samples.

Run: python3 tests/live_brochure_fetch.py
"""

import asyncio
import json
import logging

from scraper.kaufda import KaufdaScraper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    scraper = KaufdaScraper()
    samples, errors = await scraper.scrape_brochure_page_samples(
        retailers=["lidl", "edeka"],
    )
    print(f"\n== Got {len(samples)} samples, {len(errors)} errors ==\n")
    for s in samples:
        compact = {k: s.get(k) for k in (
            "store", "brochure_title", "page_number", "url", "image_url", "validity_text"
        )}
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    if errors:
        print("\n-- errors --")
        for e in errors:
            print(e)


if __name__ == "__main__":
    asyncio.run(main())
