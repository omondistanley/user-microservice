"""
Optional AI explainer integration for recommendation narratives.

Tri-provider: generic (custom endpoint), Groq, and Brave. Router tries
providers in AI_EXPLAINER_PROVIDER_ORDER; returns first non-empty narrative.
Best-effort only; recommendation engine continues without narrative on failure.
"""
from __future__ import annotations

import json
import logging
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

# Blocklist phrases that imply financial advice; narrative rejected or truncated when found
NARRATIVE_BLOCKLIST: List[str] = [
    "you should buy",
    "you should sell",
    "you ought to buy",
    "you ought to sell",
    "i recommend buying",
    "i recommend selling",
    "we recommend buying",
    "we recommend selling",
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


def is_enabled() -> bool:
    """True if any of generic, Groq, or Brave is configured."""
    return _generic_configured() or _groq_configured() or _brave_configured()


async def generate_narrative(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Try each provider in AI_EXPLAINER_PROVIDER_ORDER; return first non-empty
    narrative after post-process (blocklist + truncation).
    Returns (narrative, provider_name) or (None, None).
    """
    if not payload:
        return None, None
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
            return narrative, name
    return None, None
