"""Scraper utilities: fingerprinting, dedup, rate limiting."""

import asyncio
import hashlib
import random
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

import config

BERLIN_TZ = ZoneInfo("Europe/Berlin")
GERMAN_WEEKDAYS = {
    "montag": 0,
    "mo": 0,
    "dienstag": 1,
    "di": 1,
    "mittwoch": 2,
    "mi": 2,
    "donnerstag": 3,
    "do": 3,
    "freitag": 4,
    "fr": 4,
    "samstag": 5,
    "sa": 5,
    "sonntag": 6,
    "so": 6,
}

LOYALTY_PATTERNS: list[tuple[str, list[str]]] = [
    ("lidl_plus", ["lidl plus", "lidl+", "plus preis", "mit lidl plus"]),
    ("payback", ["payback", "mit payback"]),
    ("edeka_app", ["edeka app", "mit edeka app"]),
    ("rewe_app", ["rewe app", "mit rewe app"]),
    ("app_coupon", ["app-coupon", "app coupon", "coupon in der app", "digitaler coupon"]),
    ("kundenkarte", ["kundenkarte", "clubkarte", "karte", "treuekarte"]),
]


def fingerprint_url(url: str) -> str:
    """Return a 16-char SHA-1 hex digest of the canonical URL."""
    canonical = url.strip().rstrip("/").lower()
    return hashlib.sha1(canonical.encode()).hexdigest()[:16]


def canonical_url(base: str, href: str) -> str:
    """Resolve a potentially relative href against a base URL."""
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def extract_source_page_metadata(url: str | None) -> dict:
    """Extract brochure page provenance from a Kaufda content viewer URL."""
    result = {
        "source_viewer_url": None,
        "source_page_number": None,
    }
    if not url:
        return result

    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        page_values = query.get("page") or []
        if page_values:
            try:
                result["source_page_number"] = int(page_values[0])
            except ValueError:
                pass

        if "contentviewer" in parsed.path.lower():
            result["source_viewer_url"] = url
    except Exception:
        return result

    return result


def clean_price(text: str | None) -> float | None:
    """Extract a float price from a German-formatted string like '1.299,99 €'."""
    if not text:
        return None
    text = text.replace(".", "").replace(",", ".").replace("€", "").strip()
    match = re.search(r"[\d]+\.?[\d]*", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def clean_discount(text: str | None) -> float | None:
    """Extract discount percentage from a string like '-38%'."""
    if not text:
        return None
    match = re.search(r"[\d]+\.?[\d]*", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return None


def extract_price_candidates(text: str | None) -> list[float]:
    """Extract ordered unique EUR price candidates from free text."""
    if not text:
        return []
    matches = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}\s*€", text)
    prices: list[float] = []
    for match in matches:
        value = clean_price(match)
        if value is not None and value not in prices:
            prices.append(value)
    return prices


async def jitter_sleep() -> None:
    """Sleep a random interval to avoid rate-limiting."""
    delay = random.uniform(
        config.SCRAPER_INTER_PAGE_DELAY_MIN,
        config.SCRAPER_INTER_PAGE_DELAY_MAX,
    )
    await asyncio.sleep(delay)


def berlin_today() -> date:
    """Return today's date in the app's local timezone."""
    return datetime.now(BERLIN_TZ).date()


def format_validity_window(offer: dict) -> str | None:
    """Render a human-readable validity window from stored offer fields."""
    valid_from = offer.get("valid_from")
    valid_to = offer.get("valid_to")
    is_upcoming = bool(offer.get("is_upcoming"))
    raw_text = offer.get("validity_text")

    if valid_from and valid_to:
        if valid_from == valid_to:
            prefix = "Gültig am" if not is_upcoming else "Gültig ab"
            return f"{prefix} {valid_from}"
        return f"Gültig {valid_from} bis {valid_to}"
    if valid_from:
        prefix = "Gültig ab" if is_upcoming else "Seit"
        return f"{prefix} {valid_from}"
    if valid_to:
        return f"Gültig bis {valid_to}"
    return raw_text


def extract_loyalty_condition(text: str | None) -> dict:
    """Extract app/card/loyalty conditions from offer text."""
    result = {
        "requires_loyalty": False,
        "loyalty_program": None,
        "price_condition_text": None,
    }
    if not text:
        return result

    lowered = " ".join(text.lower().split())
    matched_program = None
    matched_phrase = None

    for program, phrases in LOYALTY_PATTERNS:
        for phrase in phrases:
            if phrase in lowered:
                matched_program = program
                matched_phrase = phrase
                break
        if matched_program:
            break

    if not matched_program:
        return result

    result["requires_loyalty"] = True
    result["loyalty_program"] = matched_program

    sentence_match = re.search(
        r"([^.!?\n]{0,80}(?:lidl plus|lidl\+|payback|edeka app|rewe app|app-coupon|app coupon|kundenkarte|clubkarte)[^.!?\n]{0,120})",
        text,
        re.IGNORECASE,
    )
    if sentence_match:
        result["price_condition_text"] = " ".join(sentence_match.group(1).split())
    else:
        result["price_condition_text"] = matched_phrase

    return result


def resolve_offer_prices(
    primary_price: float | None,
    text: str | None,
    requires_loyalty: bool,
) -> dict:
    """
    Derive standard vs loyalty price from scraped text.

    Heuristic:
    - without loyalty condition: keep primary price as standard_price
    - with loyalty condition and 2+ visible prices: lowest is loyalty_price,
      the next-lowest distinct price becomes standard_price
    - with loyalty condition and only one price: keep primary price as loyalty_price
    """
    candidates = extract_price_candidates(text)
    standard_price = primary_price
    loyalty_price = None

    if requires_loyalty:
        unique_sorted = sorted(set(candidates))
        if len(unique_sorted) >= 2:
            loyalty_price = unique_sorted[0]
            standard_price = unique_sorted[1]
        elif primary_price is not None:
            loyalty_price = primary_price
            standard_price = None

    return {
        "price": standard_price if standard_price is not None else primary_price,
        "standard_price": standard_price,
        "loyalty_price": loyalty_price,
    }


def parse_offer_validity(text: str | None, reference_date: date | None = None) -> dict:
    """Parse validity hints such as 'ab Samstag' or '16.05. bis 18.05.'."""
    result = {
        "validity_text": None,
        "valid_from": None,
        "valid_to": None,
        "is_upcoming": False,
    }
    if not text:
        return result

    ref = reference_date or berlin_today()
    compact = " ".join(text.split())
    lowered = compact.lower()

    patterns = [
        r"(gültig\s+vom\s+.+?\s+bis\s+.+?)(?:$|[|,])",
        r"(vom\s+.+?\s+bis\s+.+?)(?:$|[|,])",
        r"((?:gültig\s+)?\d{1,2}\.\d{1,2}\.?\s*(?:bis|-)\s*\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)(?:$|[|,])",
        r"((?:ab|bis|nur am)\s+(?:heute|morgen|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?))(?:$|[|,])",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact, re.IGNORECASE)
        if match:
            result["validity_text"] = match.group(1).strip()
            break

    range_match = re.search(
        r"(?:gültig\s+)?(?:vom\s+)?(?P<start>\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)\s*(?:bis|-)\s*(?P<end>\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)",
        lowered,
    )
    if range_match:
        start = _parse_german_date(range_match.group("start"), ref)
        end = _parse_german_date(range_match.group("end"), ref, fallback_year=start.year if start else None)
        if start:
            result["valid_from"] = start.isoformat()
        if end:
            result["valid_to"] = end.isoformat()
        result["is_upcoming"] = bool(start and start > ref)
        return result

    start_end_match = re.search(
        r"vom\s+(?P<start>heute|morgen|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)\s+bis\s+(?P<end>heute|morgen|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)",
        lowered,
    )
    if start_end_match:
        start = _parse_relative_or_date(start_end_match.group("start"), ref)
        end = _parse_relative_or_date(start_end_match.group("end"), ref)
        if start:
            result["valid_from"] = start.isoformat()
        if end:
            result["valid_to"] = end.isoformat()
        result["is_upcoming"] = bool(start and start > ref)
        return result

    ab_match = re.search(
        r"\bab\s+(?P<value>heute|morgen|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)",
        lowered,
    )
    if ab_match:
        start = _parse_relative_or_date(ab_match.group("value"), ref)
        if start:
            result["valid_from"] = start.isoformat()
            result["is_upcoming"] = start > ref
        return result

    bis_match = re.search(
        r"\bbis\s+(?P<value>heute|morgen|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)",
        lowered,
    )
    if bis_match:
        end = _parse_relative_or_date(bis_match.group("value"), ref)
        if end:
            result["valid_to"] = end.isoformat()
        return result

    one_day_match = re.search(
        r"\bnur am\s+(?P<value>heute|morgen|übermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so|\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?)",
        lowered,
    )
    if one_day_match:
        only = _parse_relative_or_date(one_day_match.group("value"), ref)
        if only:
            iso = only.isoformat()
            result["valid_from"] = iso
            result["valid_to"] = iso
            result["is_upcoming"] = only > ref
        return result

    return result


def _parse_relative_or_date(value: str, reference_date: date) -> date | None:
    if value in {"heute", "today"}:
        return reference_date
    if value == "morgen":
        return reference_date + timedelta(days=1)
    if value == "übermorgen":
        return reference_date + timedelta(days=2)
    if value in GERMAN_WEEKDAYS:
        return _next_weekday_on_or_after(reference_date, GERMAN_WEEKDAYS[value])
    return _parse_german_date(value, reference_date)


def _next_weekday_on_or_after(reference_date: date, target_weekday: int) -> date:
    delta = (target_weekday - reference_date.weekday()) % 7
    return reference_date + timedelta(days=delta)


def _parse_german_date(value: str, reference_date: date, fallback_year: int | None = None) -> date | None:
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(?:(\d{2,4}))?|(\d{1,2})\.(\d{1,2})", value.strip())
    if not match:
        return None

    if match.group(1) and match.group(2):
        day = int(match.group(1))
        month = int(match.group(2))
        year_raw = match.group(3)
    else:
        day = int(match.group(4))
        month = int(match.group(5))
        year_raw = None
    if year_raw:
        year = int(year_raw)
        if year < 100:
            year += 2000
    else:
        year = fallback_year or reference_date.year

    try:
        parsed = date(year, month, day)
    except ValueError:
        return None

    if not year_raw and not fallback_year and parsed < reference_date - timedelta(days=7):
        try:
            parsed = date(year + 1, month, day)
        except ValueError:
            return None
    return parsed
