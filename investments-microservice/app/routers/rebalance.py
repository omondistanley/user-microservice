from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.core.dependencies import get_current_user_id
from app.services.holdings_data_service import HoldingsDataService
from app.services.rebalance_execution import RebalanceExecutionService
from app.services.rebalance_planner import DEFAULT_PARAMS, RebalancePlanner
from app.services.recommendation_engine import RecommendationEngine
from app.services.finance_context_client import fetch_finance_context_internal

logger = logging.getLogger("rebalance_router")


SCHEMA = "investments_db"
TABLE = "portfolio_rebalance_session"


_DB_CONTEXT = {
    "host": DB_HOST or "localhost",
    "port": int(DB_PORT) if DB_PORT else 5432,
    "user": DB_USER or "postgres",
    "password": DB_PASSWORD or "postgres",
    "dbname": DB_NAME or "investments_db",
}


def _get_connection():
    return psycopg2.connect(
        host=_DB_CONTEXT["host"],
        port=_DB_CONTEXT["port"],
        user=_DB_CONTEXT["user"],
        password=_DB_CONTEXT["password"],
        dbname=_DB_CONTEXT["dbname"],
        cursor_factory=RealDictCursor,
    )


def _db_get_session(user_id: int, sell_date, trigger_type: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND sell_date = %s AND trigger_type = %s
                LIMIT 1
                ''',
                (user_id, sell_date.isoformat(), trigger_type),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _db_upsert_session(
    *,
    user_id: int,
    trigger_type: str,
    scenario: str,
    phase: str,
    sell_date,
    buy_due_date,
    payload_json: Optional[Dict[str, Any]],
    sell_requested_at: Optional[datetime],
) -> str:
    conn = _get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                f'''
                INSERT INTO "{SCHEMA}"."{TABLE}"
                    (user_id, trigger_type, scenario, phase, sell_date, buy_due_date, payload_json, sell_requested_at)
                VALUES (%s, %s, %s, %s, %s::date, %s::date, %s::jsonb, %s)
                ON CONFLICT (user_id, sell_date, trigger_type)
                DO UPDATE SET
                    scenario = EXCLUDED.scenario,
                    phase = EXCLUDED.phase,
                    buy_due_date = EXCLUDED.buy_due_date,
                    payload_json = EXCLUDED.payload_json,
                    sell_requested_at = COALESCE(EXCLUDED.sell_requested_at, "{SCHEMA}"."{TABLE}".sell_requested_at),
                    updated_at = now()
                RETURNING rebalance_session_id
                ''',
                (
                    user_id,
                    trigger_type,
                    scenario,
                    phase,
                    sell_date.isoformat(),
                    buy_due_date.isoformat() if buy_due_date else None,
                    Json(payload_json) if payload_json is not None else None,
                    sell_requested_at,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            sid = row.get("rebalance_session_id") if row else None
            if not sid:
                raise RuntimeError("Failed to create rebalance session.")
            return str(sid)
    finally:
        conn.close()


def _db_mark_sell_done(session_id: str, *, sell_completed_at: datetime) -> None:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                UPDATE "{SCHEMA}"."{TABLE}"
                SET phase = 'sell_done',
                    sell_completed_at = %s,
                    updated_at = now()
                WHERE rebalance_session_id = %s::uuid
                ''',
                (sell_completed_at, session_id),
            )
        conn.commit()
    finally:
        conn.close()


class ManualRebalanceTrigger(BaseModel):
    trigger_mode: str = Field(
        ...,
        description="Use 'scenario2' for material-change default behavior; use 'scenario1_force' to bypass material-change gate.",
    )


router = APIRouter(prefix="/api/v1", tags=["rebalance"])


@router.post("/rebalance/manual", response_model=dict)
async def manual_rebalance(
    payload: ManualRebalanceTrigger,
    user_id: int = Depends(get_current_user_id),
):
    trigger_mode = (payload.trigger_mode or "").strip().lower()
    if trigger_mode not in ("scenario2", "scenario1_force"):
        raise HTTPException(status_code=400, detail="trigger_mode must be 'scenario2' or 'scenario1_force'")

    force_scenario1 = trigger_mode == "scenario1_force"
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    trigger_type = "manual"
    existing = _db_get_session(user_id, today, trigger_type)
    if existing and str(existing.get("phase") or "") in ("sell_done", "buy_done", "no_action_done", "buy_pending"):
        return {"rebalance_session_id": str(existing.get("rebalance_session_id")), "phase": existing.get("phase"), "scenario": existing.get("scenario")}

    # Run planner inputs: holdings + ranked recommendation items.
    holdings_svc = HoldingsDataService(context=_DB_CONTEXT)
    engine = RecommendationEngine()
    planner = RebalancePlanner(DEFAULT_PARAMS)
    execution = RebalanceExecutionService()

    holdings_rows = holdings_svc.list_all_holdings_for_user(user_id)
    finance_ctx = fetch_finance_context_internal(user_id=user_id)
    rec_result = engine.run_for_user(
        user_id,
        include_ai_narratives=False,
        finance_ctx=finance_ctx,
    )
    items = rec_result.get("items") or []
    try:
        items_ranked = sorted(items, key=lambda it: (Decimal(str(it.get("score") or "0")), str(it.get("symbol") or "")), reverse=True)
    except Exception:
        items_ranked = items

    # Prev session payload for material-change trace.
    prev_payload = None
    last_sell_completed_at = None
    if existing:
        # If a manual session already exists for today, treat it as "current" and don't reuse it for material-change.
        pass
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s
                  AND NOT (trigger_type = 'manual' AND sell_date = %s::date)
                ORDER BY created_at DESC
                LIMIT 1
                ''',
                (user_id, today.isoformat()),
            )
            prev = cur.fetchone()
            if prev:
                prev_payload = prev.get("payload_json")
                last_sell_completed_at = prev.get("sell_completed_at")
    finally:
        conn.close()

    planned = planner.plan(
        now_utc=now_utc,
        trigger_type=trigger_type,
        holdings_rows=holdings_rows,
        items_ranked=items_ranked,
        prev_session_payload=prev_payload,
        last_sell_completed_at=last_sell_completed_at,
        force_scenario1=force_scenario1,
        target_scenario=None,
        finance_ctx=finance_ctx,
    )

    scenario = planned.get("scenario") or "no_action"
    if scenario == "no_action":
        sid = _db_upsert_session(
            user_id=user_id,
            trigger_type=trigger_type,
            scenario="no_action",
            phase="no_action_done",
            sell_date=today,
            buy_due_date=None,
            payload_json=planned,
            sell_requested_at=None,
        )
        return {"rebalance_session_id": sid, "phase": "no_action_done", "scenario": "no_action"}

    buy_due_date = today + timedelta(days=1)
    sid = _db_upsert_session(
        user_id=user_id,
        trigger_type=trigger_type,
        scenario=scenario,
        phase="sell_pending",
        sell_date=today,
        buy_due_date=buy_due_date,
        payload_json=planned,
        sell_requested_at=now_utc,
    )

    # If session was concurrently updated to sell_done, avoid duplicating orders.
    if existing and str(existing.get("phase") or "") == "sell_done":
        return {"rebalance_session_id": sid, "phase": "sell_done", "scenario": scenario}

    await execution.execute_sell_phase(
            user_id=user_id,
            scenario=scenario,
            rebalance_session_id=sid,
            why_lines=planned.get("why_lines") or [],
            sell_orders=planned.get("sell_orders") or [],
        )
    _db_mark_sell_done(sid, sell_completed_at=datetime.now(timezone.utc))

    # Reload to return latest phase.
    updated = _db_get_session(user_id, today, trigger_type)
    return {
        "rebalance_session_id": sid,
        "phase": updated.get("phase") if updated else "sell_done",
        "scenario": scenario,
    }

