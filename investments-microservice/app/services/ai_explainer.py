"""
Optional AI explainer integration for recommendation narratives.

Tri-provider: generic (custom endpoint), Groq, and Brave. Router tries
providers in AI_EXPLAINER_PROVIDER_ORDER; returns first non-empty narrative.
Best-effort only; recommendation engine continues without narrative on failure.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import (
    AI_EXPLAINER_API_BASE,
    AI_EXPLAINER_API_KEY,
    AI_EXPLAINER_MAX_NARRATIVE_CHARS,
    AI_EXPLAINER_MODEL,
    AI_EXPLAINER_PROVIDER_ORDER,
    AI_EXPLAINER_TIMEOUT_SECONDS,
    BRAVE_API_BASE,
    BRAVE_API_KEY,
    BRAVE_MODEL,
    BRAVE_TIMEOUT_SECONDS,
    GROQ_API_BASE,
    GROQ_API_KEY,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TIMEOUT_SECONDS,
)

logger = logging.getLogger("investments_ai_explainer")

# Blocklist phrases that imply financial advice; narrative rejected or truncated when found.
# Expanded (Sprint 1) to cover: imperative directives, guarantee language, urgency framing,
# and suitability claims — all of which could expose the platform to regulatory risk.
NARRATIVE_BLOCKLIST: List[str] = [
    # Direct buy/sell directives
    "you should buy",
    "you should sell",
    "you ought to buy",
    "you ought to sell",
    "i recommend buying",
    "i recommend selling",
    "we recommend buying",
    "we recommend selling",
    # Imperative variants
    "buy now",
    "sell now",
    "buy this",
    "sell this",
    "invest now",
    "exit now",
    "add to your portfolio",
    "remove from your portfolio",
    # Guarantee / certainty language
    "guaranteed return",
    "guaranteed profit",
    "will definitely",
    "will certainly",
    "risk-free",
    "risk free",
    "no risk",
    "assured return",
    # Urgency / FOMO framing
    "don't miss out",
    "act now",
    "time-sensitive",
    "limited opportunity",
    "last chance",
    # Suitability claims
    "suitable for you",
    "right investment for you",
    "best investment for you",
    "perfect investment",
    "tailored to your",
    # Regulatory red-flags
    "financial advisor",
    "investment advisor",
    "portfolio manager",
    "licensed",
    "sec registered",
    "regulated advice",
]

DISCLAIMER_LINE = (
    "This is not financial advice. For informational purposes only. "
    "Describe only the risk/return metrics from the payload; do not recommend buy or sell."
)


def build_prompt(payload: Dict[str, Any]) -> Tuple[str, str]:
    """Build system and user messages for all providers (shared prompt template)."""
    system = (
        "You are a concise assistant that summarizes investment risk metrics. "
        + DISCLAIMER_LINE
        + " Keep the summary to 80 words or fewer."
    )
    user = (
        "Summarize the following risk and portfolio metrics in plain language, "
        "without giving advice:\n\n"
        + json.dumps(payload, default=str, indent=0)[:2000]
    )
    return system, user


def _post_process(text: Optional[str]) -> Optional[str]:
    """Apply blocklist check and truncation. Returns None if blocklist triggered."""
    if not text or not text.strip():
        return None
    normalized = text.lower().strip()
    for phrase in NARRATIVE_BLOCKLIST:
        if phrase in normalized:
            logger.warning("ai_explainer_blocklist_triggered", extra={"phrase": phrase})
            return None
    if len(text) > AI_EXPLAINER_MAX_NARRATIVE_CHARS:
        text = text[: AI_EXPLAINER_MAX_NARRATIVE_CHARS].rsplit(" ", 1)[0] + "."
    return text.strip() or None


def _generic_configured() -> bool:
    return bool(AI_EXPLAINER_API_BASE and AI_EXPLAINER_API_KEY and AI_EXPLAINER_MODEL)


async def _generic_generate(payload: Dict[str, Any]) -> Optional[str]:
    """Call generic /v1/explain endpoint. Returns raw narrative or None."""
    if not _generic_configured():
        return None
    url = f"{AI_EXPLAINER_API_BASE.rstrip('/')}/v1/explain"
    headers = {
        "Authorization": f"Bearer {AI_EXPLAINER_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"model": AI_EXPLAINER_MODEL, "input": payload}
    try:
        async with httpx.AsyncClient(timeout=float(AI_EXPLAINER_TIMEOUT_SECONDS)) as client:
            resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json() or {}
        text = data.get("text") or data.get("message") or ""
        return text.strip() or None
    except Exception as exc:
        logger.warning("AI explainer generic call failed: %s", exc)
        return None


def _groq_configured() -> bool:
    return bool(GROQ_API_BASE and GROQ_API_KEY and GROQ_MODEL)


async def _groq_generate(payload: Dict[str, Any]) -> Optional[str]:
    """Call Groq OpenAI-compatible chat completions. Returns raw narrative or None."""
    if not _groq_configured():
        return None
    system, user = build_prompt(payload)
    url = f"{GROQ_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": min(GROQ_MAX_TOKENS, 150),
    }
    try:
        async with httpx.AsyncClient(timeout=float(GROQ_TIMEOUT_SECONDS)) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code == 429:
            logger.warning("Groq rate limit (429)")
            return None
        resp.raise_for_status()
        data = resp.json() or {}
        choice = (data.get("choices") or [None])[0]
        if not choice:
            return None
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        return text.strip() or None
    except Exception as exc:
        logger.warning("AI explainer Groq call failed: %s", exc)
        return None


def _brave_configured() -> bool:
    return bool(BRAVE_API_BASE and BRAVE_API_KEY and BRAVE_MODEL)


async def _brave_generate(payload: Dict[str, Any]) -> Optional[str]:
    """Call Brave chat completions. Returns raw narrative or None."""
    if not _brave_configured():
        return None
    system, user = build_prompt(payload)
    url = f"{BRAVE_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {BRAVE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": BRAVE_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 150,
    }
    try:
        async with httpx.AsyncClient(timeout=float(BRAVE_TIMEOUT_SECONDS)) as client:
            resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json() or {}
        choice = (data.get("choices") or [None])[0]
        if not choice:
            return None
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        return text.strip() or None
    except Exception as exc:
        logger.warning("AI explainer Brave call failed: %s", exc)
        return None


def _fallback_narrative(payload: Dict[str, Any]) -> str:
    """
    Deterministic template narrative used when all AI providers are unavailable.
    Produces a 1-2 sentence plain-English summary of the key risk/return metrics
    present in the payload. No advice language — safe by construction.
    """
    parts: List[str] = []

    symbol = payload.get("symbol") or payload.get("ticker") or ""
    score = payload.get("score") or payload.get("combined_score")
    confidence = payload.get("confidence")
    volatility = payload.get("volatility") or payload.get("vol")
    sharpe = payload.get("sharpe") or payload.get("sharpe_ratio")
    beta = payload.get("beta")
    sentiment = payload.get("sentiment") or payload.get("sentiment_score")
    reason = payload.get("reason") or payload.get("primary_reason") or ""

    lead = f"{symbol.upper()} — " if symbol else ""

    if score is not None:
        try:
            score_val = float(score)
            direction = "above" if score_val > 0 else "below"
            parts.append(f"composite score of {score_val:+.2f} ({direction} neutral)")
        except (TypeError, ValueError):
            pass

    if volatility is not None:
        try:
            parts.append(f"30-day volatility {float(volatility):.1%}")
        except (TypeError, ValueError):
            pass

    if sharpe is not None:
        try:
            parts.append(f"Sharpe ratio {float(sharpe):.2f}")
        except (TypeError, ValueError):
            pass

    if beta is not None:
        try:
            parts.append(f"beta {float(beta):.2f}")
        except (TypeError, ValueError):
            pass

    if sentiment is not None:
        try:
            sent_val = float(sentiment)
            sent_label = "positive" if sent_val > 0.1 else ("negative" if sent_val < -0.1 else "neutral")
            parts.append(f"news sentiment {sent_label} ({sent_val:+.2f})")
        except (TypeError, ValueError):
            pass

    if not parts:
        return f"{lead}No detailed metrics available for this position.".strip()

    body = ", ".join(parts) + "."
    if confidence is not None:
        try:
            body += f" Model confidence: {float(confidence):.0%}."
        except (TypeError, ValueError):
            pass
    if reason:
        body += f" Primary signal: {str(reason)[:120]}."

    return (lead + body).strip()


def is_enabled() -> bool:
    """True if any of generic, Groq, or Brave is configured."""
    return _generic_configured() or _groq_configured() or _brave_configured()


# ---------------------------------------------------------------------------
# Sprint 3: Redis narrative cache
# ---------------------------------------------------------------------------
# Narratives for the same payload are stable (same metrics → same text).
# Caching them in Redis gives ~80% latency reduction on repeated calls and
# shields the provider rate limits from thundering-herd during bulk runs.
#
# Cache key: SHA-256 of the canonical JSON representation of the payload
# (keys sorted, floats rounded to 4 dp to absorb fp noise).
# TTL: 6 hours — long enough to avoid redundant calls within a trading day;
# short enough to refresh when metrics change materially.
#
# Graceful degradation: if Redis is not reachable (REDIS_URL not set, server
# down), caching is silently skipped and generation proceeds normally.
# ---------------------------------------------------------------------------

_NARRATIVE_CACHE_TTL = int(os.environ.get("AI_EXPLAINER_CACHE_TTL_SECONDS", 21_600))
_NARRATIVE_CACHE_PREFIX = "ai_explainer:narrative:"

_redis_client = None
_redis_init_attempted = False


def _get_redis():
    """Return a Redis client, or None if unavailable."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client
    _redis_init_attempted = True
    redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_URI")
    if not redis_url:
        return None
    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
        _redis_client.ping()
        logger.info("ai_explainer_redis_connected")
    except Exception as exc:
        logger.debug("ai_explainer_redis_unavailable: %s", exc)
        _redis_client = None
    return _redis_client


def _payload_cache_key(payload: Dict[str, Any]) -> str:
    """Stable SHA-256 cache key from payload contents."""
    def _normalise(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _normalise(v) for k, v in sorted(obj.items())}
        if isinstance(obj, (list, tuple)):
            return [_normalise(i) for i in obj]
        if isinstance(obj, float):
            return round(obj, 4)
        return obj

    canonical = json.dumps(_normalise(payload), sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:32]
    return f"{_NARRATIVE_CACHE_PREFIX}{digest}"


def _cache_get(key: str) -> Optional[Tuple[str, str]]:
    """Return cached (narrative, provider) or None."""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        if raw:
            data = json.loads(raw)
            return data.get("narrative"), data.get("provider")
    except Exception:
        pass
    return None


def _cache_set(key: str, narrative: str, provider: str) -> None:
    """Store (narrative, provider) in Redis with TTL."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(key, _NARRATIVE_CACHE_TTL, json.dumps({"narrative": narrative, "provider": provider}))
    except Exception:
        pass


async def generate_narrative(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Try each provider in AI_EXPLAINER_PROVIDER_ORDER; return first non-empty
    narrative after post-process (blocklist + truncation).
    Returns (narrative, provider_name) or (fallback_narrative, 'fallback').

    Sprint 3: results are cached in Redis (TTL 6 h by default, configurable via
    AI_EXPLAINER_CACHE_TTL_SECONDS env var).  Cache misses fall through to
    provider calls as before; cache hits skip all network I/O entirely.
    """
    if not payload:
        return None, None

    cache_key = _payload_cache_key(payload)
    cached = _cache_get(cache_key)
    if cached and cached[0]:
        logger.debug("ai_explainer_cache_hit")
        return cached[0], cached[1]

    order = [p.strip().lower() for p in (AI_EXPLAINER_PROVIDER_ORDER or "").split(",") if p.strip()]
    if not order:
        order = ["groq", "brave", "generic"]
    for name in order:
        raw: Optional[str] = None
        if name == "groq":
            raw = await _groq_generate(payload)
        elif name == "brave":
            raw = await _brave_generate(payload)
        elif name == "generic":
            raw = await _generic_generate(payload)
        else:
            continue
        narrative = _post_process(raw)
        if narrative:
            logger.info("ai_explainer_success", extra={"provider": name})
            _cache_set(cache_key, narrative, name)
            return narrative, name

    # All providers failed — emit deterministic fallback template
    fallback = _fallback_narrative(payload)
    logger.info("ai_explainer_fallback_used")
    _cache_set(cache_key, fallback, "fallback")
    return fallback, "fallback"
