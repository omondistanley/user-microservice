"""
Publish expense lifecycle events to Redis channel events:expense.
If REDIS_URL is not set or publish fails, log and no-op.
"""
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import REDIS_URL

logger = logging.getLogger(__name__)

CHANNEL = "events:expense"


def publish_expense_event(event_type: str, payload: dict) -> None:
    if not REDIS_URL or not REDIS_URL.strip():
        return
    message = {
        "event_type": event_type,
        "event_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "payload": payload,
    }
    try:
        import redis
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.publish(CHANNEL, json.dumps(message, default=str))
        client.close()
    except Exception as e:
        logger.warning("events_publish_failed event_type=%s error=%s", event_type, e)


def expense_event_payload(data: dict) -> dict:
    """Build event payload from expense row/data dict."""
    out = {
        "expense_id": str(data.get("expense_id", "")),
        "user_id": data.get("user_id"),
        "category_code": data.get("category_code"),
        "amount": str(data.get("amount", "")),
        "currency": data.get("currency", "USD"),
        "date": data.get("date").isoformat() if hasattr(data.get("date"), "isoformat") else str(data.get("date", "")),
        "source": data.get("source"),
    }
    if data.get("household_id") is not None:
        out["household_id"] = str(data["household_id"])
    return out
