"""Vision node — analyzes offer images with Gemini via OpenAI-compatible API."""

import asyncio
import json
import logging
import re
from typing import Optional

from providers.vision import get_vision_client, VISION_SYSTEM_PROMPT, VISION_USER_TEMPLATE
from workflow.state import AgentState, OfferData, AnalyzedOffer
import config

logger = logging.getLogger(__name__)

# Max concurrent vision API calls
_SEMAPHORE_LIMIT = 5

# Safe defaults used when the LLM response cannot be parsed
_DEFAULT_ANALYSIS: dict = {
    "product_name": "",
    "brand":        "unbekannt",
    "condition":    "unbekannt",
    "key_features": [],
    "quality_score": 0.5,
    "deal_verdict": "Durchschnittlich",
    "tags":         [],
}


async def _analyze_single(
    offer: OfferData,
    semaphore: asyncio.Semaphore,
) -> tuple[Optional[AnalyzedOffer], Optional[str]]:
    """Call the vision model for one offer. Returns (analyzed_offer, error_msg)."""
    async with semaphore:
        image_url = offer.get("image_url")
        if not image_url:
            logger.debug("Skipping vision for %s — no image URL", offer["external_id"])
            return None, None

        client = get_vision_client()
        user_text = VISION_USER_TEMPLATE.format(
            title=offer.get("title", ""),
            price=offer.get("price") or "?",
            original_price=offer.get("original_price") or "?",
            discount=offer.get("discount_percent") or "?",
            store=offer.get("store") or "?",
        )

        for attempt in range(2):
            try:
                prefix = "" if attempt == 0 else "Antworte NUR als JSON, kein Text davor oder danach.\n"
                response = await client.chat.completions.create(
                    model=config.VISION_MODEL,
                    messages=[
                        {"role": "system", "content": VISION_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url, "detail": "low"},
                                },
                                {"type": "text", "text": prefix + user_text},
                            ],
                        },
                    ],
                    max_tokens=4096,
                    temperature=0.1,
                )
                raw = response.choices[0].message.content or ""
                data = _parse_json_response(raw)
                if data:
                    return _build_analyzed_offer(offer, data, raw), None

            except Exception as exc:
                if attempt == 1:
                    msg = f"Vision error for {offer['external_id']}: {exc}"
                    logger.warning(msg)
                    # Return safe defaults so the pipeline continues
                    return _build_analyzed_offer(offer, _DEFAULT_ANALYSIS, ""), msg

        return _build_analyzed_offer(offer, _DEFAULT_ANALYSIS, ""), None


def _parse_json_response(raw: str) -> Optional[dict]:
    """Extract the first JSON object from the LLM response string."""
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _build_analyzed_offer(offer: OfferData, data: dict, raw: str) -> AnalyzedOffer:
    """Merge vision data with the original offer into an AnalyzedOffer."""
    return AnalyzedOffer(
        external_id=  offer["external_id"],
        product_name= data.get("product_name") or offer.get("title", ""),
        brand=        data.get("brand", "unbekannt"),
        condition=    data.get("condition", "unbekannt"),
        key_features= data.get("key_features") or [],
        quality_score=float(data.get("quality_score", 0.5)),
        deal_verdict= data.get("deal_verdict", "Durchschnittlich"),
        tags=         data.get("tags") or [],
        raw_llm_response=raw,
    )


async def _analyze_batch(offers: list[OfferData]) -> tuple[list[AnalyzedOffer], list[str]]:
    semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)
    tasks = [_analyze_single(o, semaphore) for o in offers]
    results = await asyncio.gather(*tasks)

    analyzed = [r[0] for r in results if r[0] is not None]
    errors   = [r[1] for r in results if r[1] is not None]
    return analyzed, errors


def vision_node(state: AgentState) -> dict:
    """Run vision analysis on all scraped_offers. Synchronous LangGraph wrapper."""
    offers = state.get("scraped_offers", [])
    if not offers:
        return {"analyzed_offers": [], "vision_errors": []}

    logger.info("Vision node: analyzing %d offers...", len(offers))

    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _analyze_batch(offers))
                    analyzed, errors = future.result(timeout=600)
            else:
                analyzed, errors = loop.run_until_complete(_analyze_batch(offers))
        except RuntimeError:
            analyzed, errors = asyncio.run(_analyze_batch(offers))
    except Exception as exc:
        logger.error("Vision node failed: %s", exc)
        return {"analyzed_offers": [], "vision_errors": [str(exc)]}

    logger.info("Vision node: analyzed %d offers, %d errors", len(analyzed), len(errors))
    return {"analyzed_offers": analyzed, "vision_errors": errors}
