"""CRUD operations for user alerts."""

import logging
from typing import Optional
from uuid import UUID

from providers.supabase_client import get_supabase
from providers.embeddings import embed_text

logger = logging.getLogger(__name__)


def create_alert(
    user_id: str,
    name: str,
    query_text: str,
    max_price: Optional[float] = None,
    min_discount: Optional[float] = None,
    categories: Optional[list[str]] = None,
    stores: Optional[list[str]] = None,
    similarity_threshold: float = 0.70,
) -> Optional[dict]:
    """Create a new alert for a user. Returns the created row or None on error."""
    embedding = embed_text(query_text)
    try:
        result = (
            get_supabase()
            .table("alerts")
            .insert({
                "user_id":            user_id,
                "name":               name,
                "query_text":         query_text,
                "max_price":          max_price,
                "min_discount":       min_discount,
                "categories":         categories,
                "stores":             stores,
                "query_embedding":    embedding,
                "similarity_threshold": similarity_threshold,
            })
            .execute()
        )
        return (result.data or [None])[0]
    except Exception as exc:
        logger.error("create_alert failed: %s", exc)
        return None


def list_alerts(user_id: str) -> list[dict]:
    """Return all active alerts for a user."""
    try:
        result = (
            get_supabase()
            .table("alerts")
            .select("id, name, query_text, max_price, min_discount, categories, is_active, last_triggered_at")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.error("list_alerts(%s) failed: %s", user_id, exc)
        return []


def delete_alert(user_id: str, alert_id: str) -> bool:
    """Soft-delete (deactivate) an alert. Returns True on success."""
    try:
        get_supabase().table("alerts").update({"is_active": False}).eq(
            "id", alert_id
        ).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.error("delete_alert(%s) failed: %s", alert_id, exc)
        return False


def get_or_create_user(telegram_chat_id: Optional[str] = None, email: Optional[str] = None) -> Optional[dict]:
    """Return existing user or create a new one. At least one contact required."""
    if not telegram_chat_id and not email:
        return None
    try:
        sb = get_supabase()
        # Try to find existing user
        if telegram_chat_id:
            res = sb.table("users").select("*").eq("telegram_chat_id", telegram_chat_id).execute()
            if res.data:
                return res.data[0]
        if email:
            res = sb.table("users").select("*").eq("email", email).execute()
            if res.data:
                return res.data[0]

        # Create new user
        payload = {}
        if telegram_chat_id:
            payload["telegram_chat_id"] = telegram_chat_id
        if email:
            payload["email"] = email
        payload["notification_channel"] = "telegram" if telegram_chat_id else "email"

        res = sb.table("users").insert(payload).execute()
        return (res.data or [None])[0]
    except Exception as exc:
        logger.error("get_or_create_user failed: %s", exc)
        return None
