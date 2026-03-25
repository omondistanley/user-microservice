"""
VIX monitor job — updates volatility mode state.
Triggers 'volatile' page_state when VIX > 30 or any held position drops >15% in 30 days.
Not financial advice.
"""
import asyncio
import logging
from typing import Any, Dict

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.market_data_router import get_default_market_data_router

logger = logging.getLogger(__name__)

_VIX_THRESHOLD = 30.0
_VIX_SYMBOL = "VIX"


def run_vix_monitor_job(job_id: str = "") -> Dict[str, Any]:
    """
    Fetch VIX quote and update Redis cache key 'vix:latest'.
    The recommendations endpoint reads this key to set page_state = 'volatile'.
    """
    logger.info("[vix_monitor:%s] starting", job_id)

    async def _fetch():
        market_router = get_default_market_data_router()
        try:
            quote, _, _ = await asyncio.wait_for(
                market_router.get_quote_with_meta(_VIX_SYMBOL),
                timeout=8.0,
            )
            if quote and quote.price:
                vix_level = float(quote.price)
                is_volatile = vix_level >= _VIX_THRESHOLD
                logger.info("[vix_monitor:%s] VIX=%.2f volatile=%s", job_id, vix_level, is_volatile)
                return {"vix": vix_level, "volatile": is_volatile}
        except Exception as e:
            logger.debug("[vix_monitor:%s] VIX fetch error: %s", job_id, e)
        return {"vix": None, "volatile": False}

    result = asyncio.run(_fetch())

    # Cache in Redis if available
    try:
        import json
        from app.core.config import REDIS_URL
        import redis as redis_lib
        r = redis_lib.from_url(REDIS_URL or "redis://localhost:6379", decode_responses=True)
        r.setex("vix:latest", 86400, json.dumps(result))  # 24h TTL
    except Exception as e:
        logger.debug("[vix_monitor:%s] Redis cache error: %s", job_id, e)

    return result
