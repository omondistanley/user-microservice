"""
Rebalance watch job:
  - runs on an interval (e.g. hourly)
  - when a user is due for a 4-week rebalance (or via manual trigger/session creation),
    it plans and executes the "sell-now" phase and schedules the buy phase.

Sell phase execution must be idempotent:
  - we create one session per (user_id, sell_date, trigger_type) via a unique DB constraint.
  - if a session already exists and is sell_done/buy_done/no_action_done, we skip.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.alpaca_connection_service import AlpacaConnectionService
from app.services.holdings_data_service import HoldingsDataService
from app.services.rebalance_execution import RebalanceExecutionService
from app.services.rebalance_planner import DEFAULT_PARAMS, RebalancePlanner
from app.services.recommendation_engine import RecommendationEngine
from app.services.finance_context_client import fetch_finance_context_internal

logger = logging.getLogger("rebalance_watch_job")


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


def _db_get_latest_session(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                ''',
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _db_get_session_for_sell_date(user_id: int, sell_date: date, trigger_type: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND sell_date = %s AND trigger_type = %s
                LIMIT 1
                ''',
                (user_id, sell_date, trigger_type),
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
    sell_date: date,
    buy_due_date: Optional[date],
    payload_json: Optional[Dict[str, Any]],
    sell_requested_at: Optional[datetime],
    executed_fingerprint: Optional[str],
) -> str:
    conn = _get_connection()
    rebalance_session_id: Optional[str] = None
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            payload = Json(payload_json) if payload_json is not None else None
            buy_due_val = buy_due_date.isoformat() if buy_due_date else None
            cur.execute(
                f'''
                INSERT INTO "{SCHEMA}"."{TABLE}"
                    (user_id, trigger_type, scenario, phase, sell_date, buy_due_date, payload_json, execution_fingerprint, sell_requested_at)
                VALUES (%s, %s, %s, %s, %s::date, %s::date, %s::jsonb, %s, %s)
                ON CONFLICT (user_id, sell_date, trigger_type)
                DO UPDATE SET
                    scenario = EXCLUDED.scenario,
                    phase = EXCLUDED.phase,
                    buy_due_date = EXCLUDED.buy_due_date,
                    payload_json = EXCLUDED.payload_json,
                    execution_fingerprint = EXCLUDED.execution_fingerprint,
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
                    buy_due_val,
                    payload,
                    executed_fingerprint,
                    sell_requested_at,
                ),
            )
            row = cur.fetchone()
            rebalance_session_id = row.get("rebalance_session_id") if row else None
            conn.commit()
    finally:
        conn.close()

    if not rebalance_session_id:
        raise RuntimeError("Failed to create/upsert rebalance session.")
    return str(rebalance_session_id)


def _db_mark_sell_done(rebalance_session_id: str, *, sell_completed_at: datetime) -> None:
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
                (sell_completed_at, rebalance_session_id),
            )
        conn.commit()
    finally:
        conn.close()


def _should_run_sell_phase(existing: Optional[Dict[str, Any]]) -> bool:
    if not existing:
        return True
    phase = str(existing.get("phase") or "")
    # Only re-run when the sell phase is not yet completed.
    return phase == "sell_pending"


def _auto_due_today(user_id: int, today: date) -> Tuple[bool, date, Optional[Dict[str, Any]]]:
    """
    Due logic: every 28 days based on last sell_date of auto_4w sessions.
    Returns (due, sell_date_for_session, previous_session_for_material_change).
    """
    prev = _db_get_latest_session(user_id)
    # If no session exists, schedule today.
    if not prev:
        return True, today, None

    # Find last auto_4w sell date.
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND trigger_type = 'auto_4w'
                ORDER BY sell_date DESC
                LIMIT 1
                ''',
                (user_id,),
            )
            last_auto = cur.fetchone()
            if not last_auto:
                return True, today, prev
            last_sell_date = last_auto.get("sell_date")
            if not last_sell_date:
                return True, today, prev
            if (today - last_sell_date).days >= 28:
                return True, today, prev
            return False, today, prev
    finally:
        conn.close()


def _items_ranked_from_engine_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = result.get("items") or []
    try:
        return sorted(
            items,
            key=lambda it: (Decimal(str(it.get("score") or "0")), str(it.get("symbol") or "")),
            reverse=True,
        )
    except Exception:
        return items


def run_rebalance_watch_job(job_id: str = "") -> Dict[str, Any]:
    logger.info("rebalance_watch_job start job_id=%s", job_id)

    alpaca_conn_svc = AlpacaConnectionService(context=_DB_CONTEXT)
    holdings_svc = HoldingsDataService(context=_DB_CONTEXT)

    engine = RecommendationEngine()
    planner = RebalancePlanner(DEFAULT_PARAMS)
    execution = RebalanceExecutionService()

    today = datetime.now(timezone.utc).date()
    processed = 0
    skipped = 0
    executed_sells = 0
    no_action = 0
    errors: List[Dict[str, Any]] = []

    user_ids = alpaca_conn_svc.list_connection_user_ids()
    for user_id in user_ids:
        try:
            due, sell_date, prev_session = _auto_due_today(user_id, today)
            if not due:
                skipped += 1
                continue

            trigger_type = "auto_4w"
            existing = _db_get_session_for_sell_date(user_id, sell_date, trigger_type)

            if existing and not _should_run_sell_phase(existing):
                skipped += 1
                continue

            holdings_rows = holdings_svc.list_all_holdings_for_user(user_id)
            # Ensure created_at for min-hold logic exists.
            now_utc = datetime.now(timezone.utc)

            # Fetch finance context for goal-horizon-aware soft scoring.
            finance_ctx = fetch_finance_context_internal(user_id=user_id)

            # Run recommendations to get ranked candidate list.
            rec_result = engine.run_for_user(
                user_id,
                include_ai_narratives=False,
                finance_ctx=finance_ctx,
            )
            items_ranked = _items_ranked_from_engine_result(rec_result)

            prev_payload = (prev_session or {}).get("payload_json") if prev_session else None
            last_sell_completed_at = (prev_session or {}).get("sell_completed_at") if prev_session else None

            planned = planner.plan(
                now_utc=now_utc,
                trigger_type=trigger_type,
                holdings_rows=holdings_rows,
                items_ranked=items_ranked,
                prev_session_payload=prev_payload,
                last_sell_completed_at=last_sell_completed_at,
                force_scenario1=False,
                target_scenario=None,
                finance_ctx=finance_ctx,
            )

            scenario = planned.get("scenario") or "no_action"
            if scenario == "no_action":
                _db_upsert_session(
                    user_id=user_id,
                    trigger_type=trigger_type,
                    scenario="no_action",
                    phase="no_action_done",
                    sell_date=sell_date,
                    buy_due_date=None,
                    payload_json=planned,
                    sell_requested_at=None,
                    executed_fingerprint=None,
                )
                no_action += 1
                continue

            buy_due_date = sell_date + timedelta(days=1)
            rebalance_session_id = _db_upsert_session(
                user_id=user_id,
                trigger_type=trigger_type,
                scenario=scenario,
                phase="sell_pending",
                sell_date=sell_date,
                buy_due_date=buy_due_date,
                payload_json=planned,
                sell_requested_at=now_utc,
                executed_fingerprint=None,
            )

            result = asyncio.run(
                execution.execute_sell_phase(
                    user_id=user_id,
                    scenario=scenario,
                    rebalance_session_id=rebalance_session_id,
                    why_lines=planned.get("why_lines") or [],
                    sell_orders=planned.get("sell_orders") or [],
                )
            )
            _db_mark_sell_done(rebalance_session_id, sell_completed_at=datetime.now(timezone.utc))
            executed_sells += 1
            processed += 1

            logger.info(
                "rebalance_watch_job executed sell user_id=%s scenario=%s session_id=%s result=%s",
                user_id,
                scenario,
                rebalance_session_id,
                result.get("executed"),
            )
        except Exception as e:
            logger.exception("rebalance_watch_job error user_id=%s: %s", user_id, e)
            errors.append({"user_id": user_id, "error": str(e)})

    return {
        "job_id": job_id,
        "processed": processed,
        "skipped": skipped,
        "executed_sells": executed_sells,
        "no_action": no_action,
        "errors": errors,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    out = run_rebalance_watch_job(job_id="cli")
    print(out)
    sys.exit(0 if not out.get("errors") else 1)

