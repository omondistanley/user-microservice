"""Optional AI narrative — off by default; cached per scene; daily cap."""
from typing import Any

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from app.config import (
    DEMO_AI_API_KEY,
    DEMO_AI_API_URL,
    DEMO_AI_DAILY_CAP,
    DEMO_AI_ENABLED,
    DEMO_AI_MODEL,
)
from app.db import ai_usage_today, get_ai_cache, increment_ai_usage, set_ai_cache
from app.limiter_util import limiter

router = APIRouter(prefix="/demo", tags=["demo-ai"])


@router.post("/narrate")
@limiter.limit("20/hour")
async def narrate_scene(request: Request, body: dict[str, Any] = Body(...)):
    if not DEMO_AI_ENABLED or not DEMO_AI_API_KEY or not DEMO_AI_API_URL:
        raise HTTPException(status_code=503, detail="AI narrative disabled")

    scene_id = (body.get("scene_id") or "").strip()
    if not scene_id or len(scene_id) > 64:
        raise HTTPException(status_code=400, detail="scene_id required")

    cached = get_ai_cache(scene_id)
    if cached:
        return {"narration": cached, "cached": True}

    if ai_usage_today() >= DEMO_AI_DAILY_CAP:
        raise HTTPException(status_code=429, detail="Daily AI cap reached")

    prompt = (
        "Write one short sentence (max 25 words) describing a personal finance app feature. "
        f"Scene id: {scene_id}. No product names. Neutral tone."
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                DEMO_AI_API_URL,
                headers={
                    "Authorization": f"Bearer {DEMO_AI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEMO_AI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                },
            )
            r.raise_for_status()
            data = r.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not text:
                raise ValueError("empty")
    except Exception:
        raise HTTPException(status_code=502, detail="AI unavailable")

    set_ai_cache(scene_id, text)
    increment_ai_usage()
    return {"narration": text, "cached": False}
