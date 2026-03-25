"""
IRA-specific informational features endpoints.
All output is informational only — not financial advice.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import date

from app.core.dependencies import get_current_user_id
from app.services.ira_features_service import (
    get_rmd_banner,
    get_contribution_headroom,
    suggest_asset_location,
    get_roth_conversion_nudge,
)

router = APIRouter(prefix="/api/v1", tags=["ira-features"])

DISCLAIMER = "Not financial advice. For informational purposes only."


@router.get("/ira/rmd", response_model=dict)
async def get_rmd(
    dob: str = Query(..., description="Date of birth in YYYY-MM-DD format"),
    ira_balance: float = Query(..., gt=0),
    user_id: int = Depends(get_current_user_id),
):
    try:
        dob_date = date.fromisoformat(dob)
    except ValueError:
        return {"rmd": None, "error": "Invalid dob format. Use YYYY-MM-DD.", "disclaimer": DISCLAIMER}
    banner = get_rmd_banner(dob_date, ira_balance)
    return {"rmd": banner, "disclaimer": DISCLAIMER}


@router.get("/ira/contribution-headroom", response_model=dict)
async def get_headroom(
    account_type: str = Query(..., description="traditional_ira | roth_ira | hsa"),
    ytd_contributions: float = Query(0.0, ge=0),
    age: int = Query(..., ge=18, le=120),
    user_id: int = Depends(get_current_user_id),
):
    result = get_contribution_headroom(account_type, ytd_contributions, age)
    return result


@router.get("/ira/asset-location", response_model=dict)
async def get_asset_location_suggestions(user_id: int = Depends(get_current_user_id)):
    """
    Returns asset location observations based on the user's current holdings and account types.
    Informational only.
    """
    import psycopg2
    from app.core.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
    try:
        conn = psycopg2.connect(
            host=DB_HOST or "localhost",
            port=int(DB_PORT) if DB_PORT else 5432,
            user=DB_USER or "postgres",
            password=DB_PASSWORD or "postgres",
            dbname=DB_NAME or "investments_db",
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT symbol, account_type FROM holding WHERE user_id = %s AND quantity > 0",
                    (user_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        positions = [{"symbol": r[0], "account_type": r[1]} for r in rows]
    except Exception:
        positions = []
    suggestions = suggest_asset_location(positions)
    return {"suggestions": suggestions, "disclaimer": DISCLAIMER}


@router.get("/ira/roth-conversion-nudge", response_model=dict)
async def get_roth_nudge(
    trad_ira_balance: float = Query(0.0, ge=0),
    estimated_income: float = Query(0.0, ge=0),
    age: int = Query(..., ge=18, le=120),
    user_id: int = Depends(get_current_user_id),
):
    nudge = get_roth_conversion_nudge(trad_ira_balance, estimated_income, age)
    return {"nudge": nudge, "disclaimer": DISCLAIMER}
