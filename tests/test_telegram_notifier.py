"""Unit tests for notifications.telegram_notifier."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notifications.telegram_notifier import send_message, send_weekly_digest


@pytest.mark.asyncio
@patch("notifications.telegram_notifier.httpx.AsyncClient")
async def test_send_message_posts_html_payload(async_client_cls):
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    client.post.return_value = response
    async_client_cls.return_value.__aenter__.return_value = client

    ok = await send_message("123", "<b>Hallo</b>")

    assert ok is True
    client.post.assert_awaited_once()
    _, kwargs = client.post.await_args
    assert kwargs["json"] == {
        "chat_id": "123",
        "text": "<b>Hallo</b>",
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    assert kwargs["timeout"] == 15


@pytest.mark.asyncio
@patch("notifications.telegram_notifier.httpx.AsyncClient")
async def test_send_message_truncates_long_messages(async_client_cls):
    client = AsyncMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    client.post.return_value = response
    async_client_cls.return_value.__aenter__.return_value = client

    text = "x" * 5000
    await send_message("123", text)

    _, kwargs = client.post.await_args
    assert len(kwargs["json"]["text"]) == 3992
    assert kwargs["json"]["text"].endswith("\n…")


@pytest.mark.asyncio
@patch("notifications.telegram_notifier.httpx.AsyncClient")
async def test_send_message_returns_false_on_error(async_client_cls):
    client = AsyncMock()
    client.post.side_effect = RuntimeError("boom")
    async_client_cls.return_value.__aenter__.return_value = client

    ok = await send_message("123", "hi")

    assert ok is False


@pytest.mark.asyncio
async def test_send_weekly_digest_returns_false_for_empty_sections():
    assert await send_weekly_digest("123", []) is False


@pytest.mark.asyncio
@patch("notifications.telegram_notifier.send_message", new_callable=AsyncMock)
@patch("notifications.telegram_notifier.digest_html", return_value="<b>Digest</b>")
async def test_send_weekly_digest_formats_and_sends(_digest_html_mock, send_message_mock):
    send_message_mock.return_value = True

    ok = await send_weekly_digest("123", [("Liste", [{"title": "A"}])])

    assert ok is True
    send_message_mock.assert_awaited_once_with("123", "<b>Digest</b>")
