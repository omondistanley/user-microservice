"""
FinBERT sentiment on news: daily score, 7d rolling average, alert when below threshold for 2 consecutive days.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import SENTIMENT_LOOKBACK_DAYS, SENTIMENT_THRESHOLD

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
TABLE = "sentiment_snapshot"


def _get_connection(context: Dict[str, Any]):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    return psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
        cursor_factory=RealDictCursor,
    )


def run_finbert(texts: List[str]) -> float:
    """
    Run FinBERT on texts; return average score in [-1, 1] (positive=1, negative=-1, neutral=0).
    Uses ProsusAI/finbert if transformers available; else returns 0.
    """
    if not texts:
        return 0.0
    try:
        from transformers import pipeline
        pipe = pipeline("sentiment-analysis", model="ProsusAI/finbert", truncation=True, max_length=512)
        total = 0.0
        count = 0
        for t in texts:
            if not (t or str(t).strip()):
                continue
            s = str(t).strip()[:512]
            try:
                out = pipe(s)
                if out and isinstance(out, list) and out[0]:
                    label = (out[0].get("label") or "").lower()
                    score = float(out[0].get("score") or 0)
                    if "pos" in label:
                        total += score
                    elif "neg" in label:
                        total -= score
                    count += 1
            except Exception:
                continue
        if count == 0:
            return 0.0
        return max(-1.0, min(1.0, total / count))
    except Exception as e:
        logger.debug("finbert_failed %s", e)
        return 0.0


def save_snapshot(context: Dict[str, Any], symbol: str, snapshot_date: date, score: float, article_count: int) -> None:
    """Upsert sentiment_snapshot row."""
    import psycopg2
    conn = psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
    )
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute(
            f'''INSERT INTO "{SCHEMA}"."{TABLE}" (symbol, snapshot_date, score, article_count, updated_at)
               VALUES (%s, %s, %s, %s, now())
               ON CONFLICT (symbol, snapshot_date) DO UPDATE SET score = EXCLUDED.score, article_count = EXCLUDED.article_count, updated_at = now()''',
            (symbol.upper(), snapshot_date, score, article_count),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_scores(context: Dict[str, Any], symbol: str, as_of: date, days: int) -> List[Dict[str, Any]]:
    """Return list of { snapshot_date, score } for the last `days` ending at as_of."""
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        start = as_of - timedelta(days=days)
        cur.execute(
            f'SELECT snapshot_date, score FROM "{SCHEMA}"."{TABLE}" '
            "WHERE symbol = %s AND snapshot_date > %s AND snapshot_date <= %s ORDER BY snapshot_date ASC",
            (symbol.upper(), start, as_of),
        )
        return [{"snapshot_date": r["snapshot_date"], "score": float(r["score"])} for r in cur.fetchall()]
    finally:
        conn.close()


def rolling_average(scores: List[Dict[str, Any]], window: int) -> float:
    """Average of the last `window` scores."""
    if not scores or window <= 0:
        return 0.0
    tail = scores[-window:]
    return sum(s["score"] for s in tail) / len(tail)


def should_alert(context: Dict[str, Any], symbol: str, as_of: date) -> bool:
    """True if 7d rolling avg was below threshold for 2 consecutive days (using last 2 days with data)."""
    days = get_daily_scores(context, symbol, as_of, SENTIMENT_LOOKBACK_DAYS + 2)
    if len(days) < 2:
        return False
    # Rolling avg for each day (trailing 7d)
    rollings = []
    for i in range(len(days)):
        window = days[max(0, i - SENTIMENT_LOOKBACK_DAYS + 1) : i + 1]
        if window:
            rollings.append(rolling_average(window, len(window)))
    if len(rollings) < 2:
        return False
    return rollings[-1] < SENTIMENT_THRESHOLD and rollings[-2] < SENTIMENT_THRESHOLD


def compute_daily_sentiment(symbol: str, news_items: List[Dict[str, Any]]) -> float:
    """Run FinBERT on news headline+summary; return average score in [-1, 1]."""
    texts = []
    for it in news_items:
        title = it.get("title") or ""
        summary = it.get("summary_or_body") or it.get("summary") or ""
        if title or summary:
            texts.append((title + " " + summary).strip())
    return run_finbert(texts)


def get_sentiment_trend_and_summary(
    context: Dict[str, Any],
    symbol: str,
    as_of: date,
    lookback_days: int = 7,
) -> tuple:
    """
    Return (daily_scores, rolling_avg, summary_str) for use in explain/recommendations.
    summary_str is 1-2 sentences describing level and trend; empty if no data.
    """
    days = get_daily_scores(context, symbol.strip().upper(), as_of, lookback_days)
    rolling_avg = rolling_average(days, len(days)) if days else None
    summary = ""
    if days and rolling_avg is not None:
        if rolling_avg > 0.2:
            summary = f"Sentiment over the past week has been positive (7-day rolling average {rolling_avg:.2f})."
        elif rolling_avg < -0.2:
            summary = f"Sentiment over the past week has been negative (7-day rolling average {rolling_avg:.2f})."
        else:
            summary = f"Sentiment over the past week has been neutral to mixed (7-day rolling average {rolling_avg:.2f})."
        if len(days) >= 2 and days[-1]["score"] < days[0]["score"] - 0.1:
            summary += " Sentiment has turned more negative recently."
        elif len(days) >= 2 and days[-1]["score"] > days[0]["score"] + 0.1:
            summary += " Sentiment has improved recently."
    return (
        [{"date": str(d["snapshot_date"]), "score": round(d["score"], 4)} for d in days],
        round(rolling_avg, 4) if rolling_avg is not None else None,
        summary,
    )
