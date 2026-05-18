"""Unit tests for scraper.models."""

from datetime import UTC, datetime

from scraper.models import RawOffer


def test_raw_offer_default_scraped_at_is_timezone_aware_and_created_at_init():
    before = datetime.now(UTC)
    offer = RawOffer(
        external_id="abc123",
        title="Bio Apfel",
        url="https://x.de/a",
    )
    after = datetime.now(UTC)

    assert offer.scraped_at.tzinfo == UTC
    assert before <= offer.scraped_at <= after


def test_raw_offer_to_state_dict_serializes_scraped_at_isoformat():
    ts = datetime(2026, 5, 16, 12, 30, tzinfo=UTC)
    offer = RawOffer(
        external_id="abc123",
        title="Bio Apfel",
        url="https://x.de/a",
        scraped_at=ts,
    )

    state = offer.to_state_dict()

    assert state["scraped_at"] == "2026-05-16T12:30:00+00:00"
