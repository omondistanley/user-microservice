"""
Lifecycle events — informational context for financial planning.
All output is informational only — not financial advice.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
import psycopg2

from app.core.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1", tags=["lifecycle-events"])

DISCLAIMER = "Not financial advice. For informational purposes only."

VALID_EVENT_TYPES = {
    "new_job", "marriage", "baby", "inheritance", "retirement", "home_purchase",
    "divorce", "job_loss", "major_expense", "windfall",
}

EVENT_CONTEXT = {
    "new_job": "A new job may affect your income, benefits, and retirement account options.",
    "marriage": "Marriage can affect filing status, beneficiary designations, and combined financial planning.",
    "baby": "A new child may affect expenses, insurance needs, and education savings goals.",
    "inheritance": "An inheritance may affect your overall asset allocation and estate planning considerations.",
    "retirement": "Approaching retirement may affect withdrawal strategy and asset allocation.",
    "home_purchase": "A home purchase is a major financial event that affects liquidity and net worth.",
    "divorce": "Divorce may affect asset division, beneficiary designations, and financial goals.",
    "job_loss": "Job loss may affect income continuity and emergency fund needs.",
    "major_expense": "A major upcoming expense may affect your savings and investment timeline.",
    "windfall": "A windfall may create an opportunity to review goals and allocations.",
}


class LifecycleEventCreate(BaseModel):
    event_type: str = Field(..., max_length=64)
    event_date: date
    notes: Optional[str] = Field(None, max_length=500)


class LifecycleEventResponse(BaseModel):
    id: int
    event_type: str
    event_date: date
    notes: Optional[str]
    context: Optional[str]
    created_at: str


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        connect_timeout=5,
    )


@router.get("/lifecycle-events", response_model=dict)
async def list_lifecycle_events(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, event_type, event_date, notes, created_at "
                    "FROM lifecycle_events WHERE user_id = %s ORDER BY event_date DESC",
                    (user_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        events = [
            {
                "id": r[0],
                "event_type": r[1],
                "event_date": r[2].isoformat() if r[2] else None,
                "notes": r[3],
                "context": EVENT_CONTEXT.get(r[1]),
                "created_at": r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]
        return {"events": events, "disclaimer": DISCLAIMER}
    except Exception as e:
        return {"events": [], "error": str(e), "disclaimer": DISCLAIMER}


@router.post("/lifecycle-events", response_model=dict, status_code=201)
async def create_lifecycle_event(
    payload: LifecycleEventCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["id"])
    if payload.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid event_type. Valid values: {sorted(VALID_EVENT_TYPES)}")
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO lifecycle_events (user_id, event_type, event_date, notes) "
                    "VALUES (%s, %s, %s, %s) RETURNING id, event_type, event_date, notes, created_at",
                    (user_id, payload.event_type, payload.event_date, payload.notes),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
        return {
            "event": {
                "id": row[0],
                "event_type": row[1],
                "event_date": row[2].isoformat() if row[2] else None,
                "notes": row[3],
                "context": EVENT_CONTEXT.get(row[1]),
                "created_at": row[4].isoformat() if row[4] else None,
            },
            "disclaimer": DISCLAIMER,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/lifecycle-events/{event_id}", status_code=204)
async def delete_lifecycle_event(event_id: int, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM lifecycle_events WHERE id = %s AND user_id = %s",
                    (event_id, user_id),
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Event not found")
            conn.commit()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
