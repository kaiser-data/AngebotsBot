"""Send weekly digest emails via Resend (secondary notification channel)."""

import logging
from typing import Optional

import resend

import config

logger = logging.getLogger(__name__)


def _build_html_email(sections: list[tuple[str, list[dict]]]) -> str:
    """Build a styled HTML email body."""
    offer_blocks = []
    for alert_name, offers in sections:
        rows = []
        for o in offers[:5]:
            price = f"€{o['price']:.2f}" if o.get("price") else "?"
            disc  = f"-{o['discount_percent']:.0f}%" if o.get("discount_percent") else ""
            rows.append(
                f"""<tr>
                    <td style="padding:8px;border-bottom:1px solid #eee">
                        <a href="{o.get('url','')}" style="color:#6366f1;font-weight:bold">
                            {o.get('title','?')[:60]}
                        </a><br>
                        <small>{o.get('store','?')}</small>
                    </td>
                    <td style="padding:8px;border-bottom:1px solid #eee;white-space:nowrap">
                        <b>{price}</b> {disc}
                    </td>
                    <td style="padding:8px;border-bottom:1px solid #eee">
                        {o.get('deal_verdict','?')}
                    </td>
                </tr>"""
            )
        offer_blocks.append(
            f"""<h3 style="color:#6366f1;margin-top:24px">{alert_name}</h3>
            <table width="100%" style="border-collapse:collapse;font-size:14px">
                <tr style="background:#f9fafb">
                    <th style="padding:8px;text-align:left">Produkt</th>
                    <th style="padding:8px;text-align:left">Preis</th>
                    <th style="padding:8px;text-align:left">Bewertung</th>
                </tr>
                {''.join(rows)}
            </table>"""
        )

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px;color:#111">
    <h2 style="color:#6366f1">🛍️ Dein wöchentlicher Angebots-Digest</h2>
    <p>Hier sind die besten neuen Deals für deine gespeicherten Suchen:</p>
    {''.join(offer_blocks)}
    <hr style="margin-top:32px;border:none;border-top:1px solid #eee">
    <p style="color:#888;font-size:12px">
        AngebotsBot — powered by Gemini &amp; kaufda.de<br>
        Um Benachrichtigungen zu verwalten, öffne den Telegram-Bot oder die Web-App.
    </p>
</body>
</html>"""


async def send_weekly_digest(
    to_email: str,
    sections: list[tuple[str, list[dict]]],
) -> bool:
    """
    Send a weekly digest email via Resend.

    Args:
        to_email: recipient address
        sections: list of (alert_name, offers_list)
    """
    if not config.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured — skipping email")
        return False

    if not sections:
        return False

    resend.api_key = config.RESEND_API_KEY
    html_body = _build_html_email(sections)

    try:
        resend.Emails.send({
            "from":    config.RESEND_FROM_EMAIL,
            "to":      [to_email],
            "subject": "🛍️ Deine wöchentlichen Angebote",
            "html":    html_body,
        })
        return True
    except Exception as exc:
        logger.error("Resend email failed for %s: %s", to_email, exc)
        return False
