"""Unit tests for notifications.email_notifier."""

from unittest.mock import patch

import pytest

from notifications.email_notifier import _build_html_email, send_weekly_digest


def test_build_html_email_renders_sections_and_offer_rows():
    sections = [
        (
            "Kaffee",
            [
                {
                    "title": "Crema Bohnen",
                    "url": "https://x.de/c",
                    "store": "Aldi",
                    "price": 9.99,
                    "discount_percent": 23,
                    "deal_verdict": "Sehr gut",
                }
            ],
        )
    ]

    out = _build_html_email(sections)

    assert "<!DOCTYPE html>" in out
    assert "Dein wöchentlicher Angebots-Digest" in out
    assert "<h3 style=\"color:#6366f1;margin-top:24px\">Kaffee</h3>" in out
    assert "Crema Bohnen" in out
    assert "Aldi" in out
    assert "<b>€9.99</b> -23%" in out
    assert "Sehr gut" in out


@patch("notifications.email_notifier.resend.Emails.send")
@patch("notifications.email_notifier.config.RESEND_API_KEY", "test-key")
@patch(
    "notifications.email_notifier.config.RESEND_FROM_EMAIL",
    "AngebotsBot <bot@example.de>",
)
@pytest.mark.asyncio
async def test_send_weekly_digest_sends_email(send):
    sections = [("Milch", [{"title": "Bio Milch", "url": "https://x.de/m"}])]

    ok = await send_weekly_digest("user@example.de", sections)

    assert ok is True
    payload = send.call_args.args[0]
    assert payload["from"] == "AngebotsBot <bot@example.de>"
    assert payload["to"] == ["user@example.de"]
    assert payload["subject"] == "🛍️ Deine wöchentlichen Angebote"
    assert "Bio Milch" in payload["html"]


@patch("notifications.email_notifier.resend.Emails.send")
@patch("notifications.email_notifier.config.RESEND_API_KEY", "")
@pytest.mark.asyncio
async def test_send_weekly_digest_skips_without_api_key(send):
    ok = await send_weekly_digest("user@example.de", [("A", [{"title": "X"}])])

    assert ok is False
    send.assert_not_called()


@patch("notifications.email_notifier.resend.Emails.send")
@patch("notifications.email_notifier.config.RESEND_API_KEY", "test-key")
@pytest.mark.asyncio
async def test_send_weekly_digest_returns_false_for_empty_sections(send):
    ok = await send_weekly_digest("user@example.de", [])

    assert ok is False
    send.assert_not_called()


@patch("notifications.email_notifier.resend.Emails.send", side_effect=RuntimeError("boom"))
@patch("notifications.email_notifier.config.RESEND_API_KEY", "test-key")
@pytest.mark.asyncio
async def test_send_weekly_digest_handles_send_failure(_send):
    ok = await send_weekly_digest("user@example.de", [("A", [{"title": "X"}])])

    assert ok is False
