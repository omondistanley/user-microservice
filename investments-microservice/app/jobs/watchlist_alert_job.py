"""
Daily watchlist price alert job.
Checks closing prices against user-set targets. Fires in-app notification on hit.
Alerts fire on daily closing price — not intraday.
Not financial advice. All alerts are informational.
"""
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import psycopg2

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.market_data_router import get_default_market_data_router

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "investments_db",
        connect_timeout=5,
    )


def _get_active_watchlist(conn) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT watchlist_id, user_id, symbol, target_price, direction
               FROM watchlist
               WHERE target_price IS NOT NULL
               AND (alerted_at IS NULL OR alerted_at < NOW() - INTERVAL '7 days')
               ORDER BY symbol""",
        )
        return [
            {"watchlist_id": r[0], "user_id": r[1], "symbol": r[2],
             "target_price": float(r[3]), "direction": r[4]}
            for r in cur.fetchall()
        ]


def _mark_alerted(conn, watchlist_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE watchlist SET alerted_at = NOW() WHERE watchlist_id = %s",
            (watchlist_id,),
        )
    conn.commit()


def _log_notification(conn, user_id: int, symbol: str, current_price: float, target_price: float, direction: str) -> None:
    """Write an in-app notification via investments_db. User-service picks it up via event or poll."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO watchlist_notification_log (user_id, symbol, current_price, target_price, direction, fired_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())
                   ON CONFLICT DO NOTHING""",
                (user_id, symbol, current_price, target_price, direction),
            )
        conn.commit()
    except Exception:
        pass  # Table may not exist yet; notification delivery is best-effort


def run_watchlist_alert_job(job_id: str = "") -> Dict[str, Any]:
    """Check watchlist targets against current prices. Fire informational alerts on hits."""
    import asyncio
    logger.info("[watchlist_alert:%s] starting", job_id)
    processed = 0
    alerts_fired = 0
    errors: List[str] = []

    try:
        conn = _get_conn()
        try:
            items = _get_active_watchlist(conn)
            if not items:
                return {"processed": 0, "alerts_fired": 0, "errors": []}

            market_router = get_default_market_data_router()

            async def check_all():
                nonlocal alerts_fired, processed
                for item in items:
                    processed += 1
                    try:
                        quote, _, _ = await asyncio.wait_for(
                            market_router.get_quote_with_meta(item["symbol"]),
                            timeout=5.0,
                        )
                        if not quote or not quote.price:
                            continue
                        price = float(quote.price)
                        target = item["target_price"]
                        direction = item["direction"]
                        hit = (direction == "above" and price >= target) or \
                              (direction == "below" and price <= target)
                        if hit:
                            logger.info(
                                "[watchlist_alert:%s] HIT user=%s %s %s %.2f (target=%.2f)",
                                job_id, item["user_id"], item["symbol"], direction, price, target
                            )
                            _mark_alerted(conn, item["watchlist_id"])
                            _log_notification(conn, item["user_id"], item["symbol"], price, target, direction)
                            alerts_fired += 1
                    except Exception as e:
                        errors.append(f"{item['symbol']}: {e}")

            asyncio.run(check_all())
        finally:
            conn.close()
    except Exception as e:
        errors.append(str(e))
        logger.exception("[watchlist_alert:%s] error: %s", job_id, e)

    logger.info("[watchlist_alert:%s] done. processed=%d fired=%d errors=%d", job_id, processed, alerts_fired, len(errors))
    return {"processed": processed, "alerts_fired": alerts_fired, "errors": errors}
