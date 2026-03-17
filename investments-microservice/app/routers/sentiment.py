"""
Sentiment API: last 7d trend per symbol (optional).
"""
from datetime import date

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user_id
from app.services.sentiment_service import get_daily_scores, rolling_average
from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, SENTIMENT_LOOKBACK_DAYS

router = APIRouter(prefix="/api/v1", tags=["sentiment"])


def _db_context():
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


@router.get("/sentiment/{symbol}", response_model=dict)
async def get_sentiment_trend(
    symbol: str,
    user_id: int = Depends(get_current_user_id),
):
    """Last 7 days sentiment scores and rolling average for the symbol."""
    context = _db_context()
    today = date.today()
    days = get_daily_scores(context, symbol.strip().upper(), today, SENTIMENT_LOOKBACK_DAYS)
    rolling_avg = rolling_average(days, len(days)) if days else None
    return {
        "symbol": symbol.strip().upper(),
        "daily_scores": [{"date": str(d["snapshot_date"]), "score": d["score"]} for d in days],
        "rolling_avg_7d": round(rolling_avg, 4) if rolling_avg is not None else None,
    }

