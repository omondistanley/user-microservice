"""
Watchlist CRUD endpoints with price alert support.
Not financial advice. For informational purposes only.
"""
import logging
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.core.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["watchlist"])


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "investments_db",
        connect_timeout=5,
    )


class WatchlistCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    target_price: Optional[float] = None
    direction: str = Field(default="below", pattern="^(above|below)$")
    notes: Optional[str] = Field(None, max_length=512)


class WatchlistUpdate(BaseModel):
    target_price: Optional[float] = None
    direction: Optional[str] = Field(None, pattern="^(above|below)$")
    notes: Optional[str] = Field(None, max_length=512)


@router.get("/watchlist", response_model=dict)
async def list_watchlist(user_id: int = Depends(get_current_user_id)):
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT watchlist_id, symbol, target_price, direction, notes, alerted_at, created_at "
                    "FROM watchlist WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,),
                )
                rows = cur.fetchall()
                items = [
                    {
                        "watchlist_id": r[0], "symbol": r[1], "target_price": float(r[2]) if r[2] else None,
                        "direction": r[3], "notes": r[4], "alerted_at": str(r[5]) if r[5] else None,
                        "created_at": str(r[6]),
                    }
                    for r in rows
                ]
        finally:
            conn.close()
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error("list_watchlist error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load watchlist")


@router.post("/watchlist", response_model=dict, status_code=201)
async def create_watchlist_item(
    payload: WatchlistCreate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO watchlist (user_id, symbol, target_price, direction, notes)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (user_id, symbol) DO UPDATE
                           SET target_price = EXCLUDED.target_price,
                               direction = EXCLUDED.direction,
                               notes = EXCLUDED.notes,
                               updated_at = NOW()
                       RETURNING watchlist_id, symbol, target_price, direction, notes, created_at""",
                    (user_id, payload.symbol.upper(), payload.target_price, payload.direction, payload.notes),
                )
                row = cur.fetchone()
                conn.commit()
        finally:
            conn.close()
        return {
            "watchlist_id": row[0], "symbol": row[1],
            "target_price": float(row[2]) if row[2] else None,
            "direction": row[3], "notes": row[4], "created_at": str(row[5]),
            "disclaimer": "Price alerts are informational. Past price levels do not indicate future performance.",
        }
    except Exception as e:
        logger.error("create_watchlist error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create watchlist item")


@router.delete("/watchlist/{watchlist_id}", status_code=204)
async def delete_watchlist_item(
    watchlist_id: int,
    user_id: int = Depends(get_current_user_id),
):
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM watchlist WHERE watchlist_id = %s AND user_id = %s",
                    (watchlist_id, user_id),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error("delete_watchlist error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete watchlist item")
