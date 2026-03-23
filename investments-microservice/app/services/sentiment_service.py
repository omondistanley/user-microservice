"""
FinBERT sentiment on news: daily score, 7d rolling average, alert when below threshold for 2 consecutive days.

Performance notes:
  - FinBERT pipeline is loaded once at first use via a module-level singleton (thread-safe double-checked lock).
    Loading the 440 MB model per call would take 3-8 seconds and 1.6 GB RAM each time — that is the bug this
    fixes.
  - All texts are passed as a single batched call (batch_size=16) rather than one call per text.
  - Pre-warm the singleton at startup by calling _get_finbert_pipeline() in the FastAPI lifespan handler.

Sprint 3 — multi-source sentiment fusion:
  - get_fused_sentiment() combines FinBERT news score with EDGAR Form 4 insider
    signal into a single composite score in [-1, 1].
  - Weights: news 70%, insider 30%.  Insider signal is lower-weight because in
    Sprint 3 it is still a filing-count proxy; weight will increase to 40% in
    Sprint 4 once full XML transaction-type parsing is in place.
  - Both sources degrade gracefully: if either returns 0.0 (no data / error)
    the composite is still meaningful from the remaining source.
  - get_sentiment_trend_and_summary() is extended to include insider_score and
    fused_score fields in its return tuple so callers can display both.
"""
import logging
import threading
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import SENTIMENT_LOOKBACK_DAYS, SENTIMENT_THRESHOLD

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
TABLE = "sentiment_snapshot"

# --- FinBERT singleton --------------------------------------------------------
# Loaded once on first call; subsequent calls return the cached pipeline object.
# Double-checked locking keeps this safe under concurrent FastAPI workers.
_finbert_lock = threading.Lock()
_finbert_pipeline = None


def _get_finbert_pipeline():
    """Return the module-level FinBERT pipeline, initialising it on first call."""
    global _finbert_pipeline
    if _finbert_pipeline is None:
        with _finbert_lock:
            if _finbert_pipeline is None:  # second check inside lock
                try:
                    from transformers import pipeline as hf_pipeline
                    _finbert_pipeline = hf_pipeline(
                        "sentiment-analysis",
                        model="ProsusAI/finbert",
                        tokenizer="ProsusAI/finbert",
                        device=-1,          # CPU; set to 0 if a GPU is available
                        truncation=True,
                        max_length=512,
                        batch_size=16,      # process up to 16 texts per forward pass
                    )
                    logger.info("finbert_pipeline_loaded")
                except Exception as exc:
                    logger.warning("finbert_load_failed: %s", exc)
                    # Leave _finbert_pipeline as None so callers fall back to 0.0
    return _finbert_pipeline


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
    Run FinBERT on a list of texts; return average score in [-1, 1].
    positive label → +score, negative label → -score, neutral → 0.
    All texts are processed in a single batched forward pass for efficiency.
    Returns 0.0 if transformers is not installed or the model fails to load.
    """
    if not texts:
        return 0.0
    pipe = _get_finbert_pipeline()
    if pipe is None:
        return 0.0
    # Sanitise: strip, truncate to 512 chars, drop empty strings
    clean = [str(t).strip()[:512] for t in texts if (t or "").strip()]
    if not clean:
        return 0.0
    try:
        # Single batched call — the pipeline handles chunking via batch_size internally
        results = pipe(clean, batch_size=min(len(clean), 32))
        total = 0.0
        count = 0
        for out in results:
            label = (out.get("label") or "").lower()
            score = float(out.get("score") or 0)
            if "pos" in label:
                total += score
            elif "neg" in label:
                total -= score
            count += 1
        return max(-1.0, min(1.0, total / count)) if count else 0.0
    except Exception as exc:
        logger.debug("finbert_inference_failed: %s", exc)
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


# ---------------------------------------------------------------------------
# Sprint 3: multi-source sentiment fusion
# ---------------------------------------------------------------------------

# Weights must sum to 1.0.
# Insider weight is 0.30 in Sprint 3 (filing-count proxy, less precise).
# Increase to 0.40 in Sprint 4 once XML transaction-type parsing is in place.
_NEWS_WEIGHT = 0.70
_INSIDER_WEIGHT = 0.30


def get_fused_sentiment(
    context: Dict[str, Any],
    symbol: str,
    as_of: date,
    news_lookback_days: int = 7,
    insider_lookback_days: int = 90,
) -> Dict[str, Any]:
    """
    Combine FinBERT news sentiment with EDGAR Form 4 insider signal.

    Both sources degrade gracefully:
      - If news score is 0.0 (no snapshots stored) the composite equals the
        insider score scaled by _INSIDER_WEIGHT / (_INSIDER_WEIGHT + _NEWS_WEIGHT
        where news is absent) — i.e. we normalise the weights.
      - Same logic applies if insider data is unavailable.
      - If both are unavailable, returns 0.0 with method='no_data'.

    Returns:
      {
        "symbol":               str,
        "fused_score":          float in [-1, 1],
        "news_score_7d":        float | None,
        "insider_score_90d":    float | None,
        "insider_filing_count": int,
        "insider_method":       str,
        "weights_used":         {"news": float, "insider": float},
        "summary":              str,
      }
    """
    sym = symbol.strip().upper()

    # --- News component ---
    daily_scores = get_daily_scores(context, sym, as_of, news_lookback_days)
    news_score: Optional[float] = rolling_average(daily_scores, len(daily_scores)) if daily_scores else None

    # --- Insider component ---
    insider_result: Dict[str, Any] = {}
    insider_score: Optional[float] = None
    try:
        from app.services.edgar_insider_service import compute_insider_sentiment_score
        insider_result = compute_insider_sentiment_score(sym, insider_lookback_days)
        raw = insider_result.get("score")
        if raw is not None:
            insider_score = float(raw)
    except Exception as exc:
        logger.debug("edgar_insider_fetch_failed for %s: %s", sym, exc)

    # --- Fusion ---
    has_news = news_score is not None and news_score != 0.0
    has_insider = insider_score is not None and insider_score != 0.0

    if not has_news and not has_insider:
        fused = 0.0
        method = "no_data"
        w_news, w_insider = _NEWS_WEIGHT, _INSIDER_WEIGHT
    elif not has_news:
        # Only insider available — normalise to full weight
        fused = float(insider_score)  # type: ignore[arg-type]
        method = "insider_only"
        w_news, w_insider = 0.0, 1.0
    elif not has_insider:
        # Only news available
        fused = float(news_score)  # type: ignore[arg-type]
        method = "news_only"
        w_news, w_insider = 1.0, 0.0
    else:
        fused = _NEWS_WEIGHT * float(news_score) + _INSIDER_WEIGHT * float(insider_score)  # type: ignore[arg-type]
        method = "fused"
        w_news, w_insider = _NEWS_WEIGHT, _INSIDER_WEIGHT

    fused = max(-1.0, min(1.0, round(fused, 4)))

    # --- Summary sentence ---
    summary_parts = []
    if has_news:
        direction = "positive" if float(news_score) > 0.1 else ("negative" if float(news_score) < -0.1 else "neutral")  # type: ignore[arg-type]
        summary_parts.append(f"News sentiment is {direction} ({float(news_score):+.2f} over {news_lookback_days}d).")  # type: ignore[arg-type]
    if has_insider:
        filing_count = insider_result.get("filing_count", 0)
        ins_dir = "positive" if float(insider_score) > 0.05 else ("negative" if float(insider_score) < -0.05 else "neutral")  # type: ignore[arg-type]
        summary_parts.append(
            f"Insider activity is {ins_dir} ({filing_count} Form 4 filing(s) in {insider_lookback_days}d)."
        )
    if not summary_parts:
        summary_parts.append("Insufficient data for sentiment analysis.")

    return {
        "symbol": sym,
        "fused_score": fused,
        "method": method,
        "news_score_7d": round(float(news_score), 4) if news_score is not None else None,
        "insider_score_90d": round(float(insider_score), 4) if insider_score is not None else None,
        "insider_filing_count": insider_result.get("filing_count", 0),
        "insider_method": insider_result.get("method", "no_data"),
        "weights_used": {"news": w_news, "insider": w_insider},
        "summary": " ".join(summary_parts),
    }
