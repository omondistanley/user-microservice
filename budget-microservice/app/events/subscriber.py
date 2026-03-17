"""
Subscribe to events:expense and react to expense.created/updated/deleted.
Runs in a background task; on each event optionally re-runs budget alert evaluation for that user.
"""
import asyncio
import json
import logging
from datetime import date

from app.core.config import REDIS_URL
from app.jobs.budget_alert_processor import evaluate_budget_alerts

logger = logging.getLogger(__name__)

CHANNEL = "events:expense"
EVENT_TYPES = ("expense.created", "expense.updated", "expense.deleted")


def _handle_message_sync(message: dict) -> None:
    event_type = message.get("event_type")
    if event_type not in EVENT_TYPES:
        return
    payload = message.get("payload") or {}
    user_id = payload.get("user_id")
    if user_id is None:
        return
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return
    try:
        evaluate_budget_alerts(as_of_date=date.today(), user_id=user_id)
    except Exception as e:
        logger.warning("event_handler_failed event_type=%s user_id=%s error=%s", event_type, user_id, e)


async def run_subscriber() -> None:
    if not REDIS_URL or not REDIS_URL.strip():
        logger.info("events_subscriber_skipped REDIS_URL not set")
        return
    try:
        from redis.asyncio import Redis
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await redis.ping()
    except Exception as e:
        logger.warning("events_subscriber_redis_failed url=%s error=%s", REDIS_URL, e)
        return
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    logger.info("events_subscriber_started channel=%s", CHANNEL)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if not data:
                continue
            try:
                if isinstance(data, str):
                    message = json.loads(data)
                else:
                    message = data
                await asyncio.to_thread(_handle_message_sync, message)
            except Exception as e:
                logger.warning("events_subscriber_parse_error data=%s error=%s", data, e)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.close()
        await redis.aclose()
        logger.info("events_subscriber_stopped channel=%s", CHANNEL)
