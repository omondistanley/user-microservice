"""
Async webhook processor:
- claims pending/retryable events from users_db.webhook_event
- forwards provider events to downstream services
- retries with exponential backoff
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    EXPENSE_SERVICE_INTERNAL_URL,
    INTERNAL_API_KEY,
    WEBHOOK_BATCH_SIZE,
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_RETRY_BASE_SECONDS,
)

SCHEMA = "users_db"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def _claim_batch(limit: int) -> list[dict[str, Any]]:
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            f"""
            WITH cte AS (
                SELECT id
                FROM "{SCHEMA}".webhook_event
                WHERE status IN ('pending', 'failed')
                  AND next_retry_at <= now()
                  AND attempt_count < %s
                ORDER BY created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE "{SCHEMA}".webhook_event e
            SET status = 'processing',
                attempt_count = e.attempt_count + 1
            FROM cte
            WHERE e.id = cte.id
            RETURNING e.id, e.provider, e.event_id, e.payload_json, e.attempt_count
            """,
            (WEBHOOK_MAX_ATTEMPTS, max(1, limit)),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _mark_processed(event_id_pk: int) -> None:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE "{SCHEMA}".webhook_event
            SET status = 'processed',
                processed_at = now(),
                last_error = NULL
            WHERE id = %s
            """,
            (event_id_pk,),
        )
    finally:
        conn.close()


def _mark_failed(event_id_pk: int, attempt_count: int, error: str) -> None:
    delay = WEBHOOK_RETRY_BASE_SECONDS * (2 ** max(0, attempt_count - 1))
    next_retry = datetime.now(timezone.utc) + timedelta(seconds=min(delay, 3600))
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE "{SCHEMA}".webhook_event
            SET status = 'failed',
                last_error = %s,
                next_retry_at = %s,
                processed_at = CASE WHEN attempt_count >= %s THEN now() ELSE processed_at END
            WHERE id = %s
            """,
            (error[:4000], next_retry, WEBHOOK_MAX_ATTEMPTS, event_id_pk),
        )
    finally:
        conn.close()


def _dispatch_to_expense(provider: str, event_id: str, payload: Any) -> None:
    if not EXPENSE_SERVICE_INTERNAL_URL:
        return
    headers = {"content-type": "application/json"}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    body = {
        "provider": provider,
        "event_id": event_id,
        "payload": payload if isinstance(payload, dict) else {},
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            f"{EXPENSE_SERVICE_INTERNAL_URL}/internal/v1/providers/webhook-event",
            headers=headers,
            json=body,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"downstream_status:{resp.status_code}")


def run_once(limit: Optional[int] = None) -> dict[str, int]:
    batch_size = int(limit) if limit else WEBHOOK_BATCH_SIZE
    batch = _claim_batch(batch_size)
    processed = 0
    failed = 0
    for row in batch:
        try:
            _dispatch_to_expense(
                provider=str(row.get("provider") or "").lower(),
                event_id=str(row.get("event_id") or ""),
                payload=row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {},
            )
            _mark_processed(int(row["id"]))
            processed += 1
        except Exception as e:
            _mark_failed(int(row["id"]), int(row.get("attempt_count") or 1), str(e))
            failed += 1
    return {"claimed": len(batch), "processed": processed, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description="Process pending webhook events.")
    parser.add_argument("--limit", type=int, default=WEBHOOK_BATCH_SIZE)
    args = parser.parse_args()
    result = run_once(limit=args.limit)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
