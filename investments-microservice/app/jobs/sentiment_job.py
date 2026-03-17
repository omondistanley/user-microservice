"""
Daily sentiment job: FinBERT on news per held symbol; save snapshot; publish sentiment.alert if below threshold 2 days.
Run: python -m app.jobs.sentiment_job
"""
import json
import logging
import sys
from datetime import date, timedelta, timezone
from typing import Dict, List, Set, Tuple

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    REDIS_URL,
    SENTIMENT_LOOKBACK_DAYS,
)
from app.services.holdings_data_service import HoldingsDataService
from app.services.news_router import get_news_for_symbol
from app.services.sentiment_service import (
    compute_daily_sentiment,
    get_daily_scores,
    rolling_average,
    save_snapshot,
    should_alert,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _db_context():
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


def run_sentiment_job() -> dict:
    """
    For each symbol held by any user: fetch news, run FinBERT, save daily snapshot.
    For each (user_id, symbol) check should_alert; if true, publish sentiment.alert to Redis.
    Returns { symbols_processed, alerts_published }.
    """
    context = _db_context()
    svc = HoldingsDataService(context=context)
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(
        host=context["host"], port=context["port"], user=context["user"],
        password=context["password"], dbname=context["dbname"],
        cursor_factory=RealDictCursor,
    )
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id, symbol FROM investments_db.holding")
    user_symbols: List[Tuple[int, str]] = [(r["user_id"], (r["symbol"] or "").strip().upper()) for r in cur.fetchall() if (r.get("symbol") or "").strip()]
    conn.close()
    symbols_done: Set[str] = set()
    today = date.today()
    for _, symbol in user_symbols:
        if symbol in symbols_done:
            continue
        symbols_done.add(symbol)
        try:
            news = get_news_for_symbol(symbol, limit=20)
            score = compute_daily_sentiment(symbol, news)
            save_snapshot(context, symbol, today, score, len(news))
        except Exception as e:
            logger.warning("sentiment_symbol_failed symbol=%s error=%s", symbol, e)
    alerts = 0
    if REDIS_URL:
        try:
            import redis
            r = redis.Redis.from_url(REDIS_URL)
            for user_id, symbol in user_symbols:
                if not should_alert(context, symbol, today):
                    continue
                days = get_daily_scores(context, symbol, today, SENTIMENT_LOOKBACK_DAYS)
                rolling_avg = rolling_average(days, len(days)) if days else 0
                payload = {
                    "event": "sentiment.alert",
                    "user_id": user_id,
                    "symbol": symbol,
                    "rolling_avg": rolling_avg,
                    "message": f"Negative sentiment building on {symbol} (7d avg: {rolling_avg:.2f})",
                }
                r.publish("events:sentiment", json.dumps(payload))
                alerts += 1
        except Exception as e:
            logger.warning("redis_sentiment_publish %s", e)
    return {"symbols_processed": len(symbols_done), "alerts_published": alerts}


if __name__ == "__main__":
    result = run_sentiment_job()
    logger.info("sentiment_job result=%s", result)
    sys.exit(0)
