"""News API: Benzinga-led pipeline with Finnhub supplement."""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user_id
from app.services.news_router import get_news_for_symbols

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["news"])


@router.get("/news", response_model=dict)
async def get_news(
    symbols: str = Query(..., description="Comma-separated symbols, e.g. AAPL,VOO"),
    limit: int = Query(20, ge=1, le=50, description="Max number of news items"),
    user_id: int = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Fetch news for the given symbols (Benzinga first, then Finnhub supplement)."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return {"items": []}
    items = get_news_for_symbols(sym_list, limit_per_symbol=max(5, limit // len(sym_list)), max_total=limit)
    return {"items": items}
