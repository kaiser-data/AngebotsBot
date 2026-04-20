"""Send Telegram messages and digests for the weekly notification system."""

import logging
import httpx

import config
from bot.formatters import digest_html

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: str, html_text: str) -> bool:
    """Send an HTML-formatted message to a Telegram chat. Returns True on success."""
    if len(html_text) > 4000:
        html_text = html_text[:3990] + "\n…"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id":    chat_id,
                    "text":       html_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Telegram send_message failed for %s: %s", chat_id, exc)
            return False


async def send_weekly_digest(
    chat_id: str,
    sections: list[tuple[str, list[dict]]],
) -> bool:
    """
    Send a weekly digest to a Telegram chat.

    Args:
        chat_id:  Telegram chat ID string
        sections: List of (alert_name, list_of_offers)
    """
    if not sections:
        return False

    html = digest_html(sections)
    return await send_message(chat_id, html)
