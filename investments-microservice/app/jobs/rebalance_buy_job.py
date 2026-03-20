"""
Rebalance buy job:
  - runs on an interval (e.g. hourly)
  - finds rebalance sessions whose sell phase is done and whose buy_due_date <= today
  - re-computes buy orders (next-day re-check) and executes the "buy-next-day" phase
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.alpaca_connection_service import AlpacaConnectionService
from app.services.holdings_data_service import HoldingsDataService
from app.services.rebalance_execution import RebalanceExecutionService
from app.services.rebalance_planner import DEFAULT_PARAMS, RebalanceChurnParams, RebalancePlanner
from app.services.recommendation_engine import RecommendationEngine
from app.services.finance_context_client import fetch_finance_context_internal

logger = logging.getLogger("rebalance_buy_job")


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


def _db_list_due_sell_done_sessions(today: date) -> List[Dict[str, Any]]:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE phase = 'sell_done'
                  AND buy_due_date IS NOT NULL
                  AND buy_due_date <= %s::date
                ORDER BY buy_due_date ASC, created_at ASC
                ''',
                (today.isoformat(),),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _db_mark_buy_pending(session_id: str, *, requested_at: datetime) -> None:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                UPDATE "{SCHEMA}"."{TABLE}"
                SET phase = 'buy_pending',
                    buy_requested_at = %s,
                    updated_at = now()
                WHERE rebalance_session_id = %s::uuid
                  AND phase = 'sell_done'
                ''',
                (requested_at, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def _db_mark_buy_done(session_id: str, *, completed_at: datetime) -> None:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                UPDATE "{SCHEMA}"."{TABLE}"
                SET phase = 'buy_done',
                    buy_completed_at = %s,
                    updated_at = now()
                WHERE rebalance_session_id = %s::uuid
                ''',
                (completed_at, session_id),
            )
        conn.commit()
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


def run_rebalance_buy_job(job_id: str = "") -> Dict[str, Any]:
    logger.info("rebalance_buy_job start job_id=%s", job_id)

    execution = RebalanceExecutionService()
    engine = RecommendationEngine()

    today = datetime.now(timezone.utc).date()

    alpaca_conn_svc = AlpacaConnectionService(context=_DB_CONTEXT)
    holdings_svc = HoldingsDataService(context=_DB_CONTEXT)

    sessions = _db_list_due_sell_done_sessions(today)
    if not sessions:
        return {"job_id": job_id, "processed": 0, "executed_buys": 0, "skipped": 0, "errors": []}

    processed = 0
    executed_buys = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    for sess in sessions:
        session_id = str(sess.get("rebalance_session_id") or "")
        try:
            if not session_id:
                continue

            user_id = int(sess.get("user_id"))
            trigger_type = str(sess.get("trigger_type") or "auto_4w")
            scenario = str(sess.get("scenario") or "scenario2")

            # Mark buy_pending immediately to prevent duplicate placements.
            now_utc = datetime.now(timezone.utc)
            _db_mark_buy_pending(session_id, requested_at=now_utc)

            holdings_rows = holdings_svc.list_all_holdings_for_user(user_id)

            # Simulate post-sell holdings by removing sold symbols from sell phase plan.
            payload_json = sess.get("payload_json") if isinstance(sess.get("payload_json"), dict) else None
            sell_orders_planned = []
            if payload_json:
                sell_orders_planned = payload_json.get("sell_orders") or []
            sold_symbols = {str(s.get("symbol") or "").upper() for s in sell_orders_planned if s.get("symbol")}
            holdings_after_sell = [h for h in holdings_rows if str(h.get("symbol") or "").upper() not in sold_symbols]

            # Fetch finance context for goal-horizon-aware soft scoring.
            finance_ctx = fetch_finance_context_internal(user_id=user_id)

            # Re-run recommendations for next-day re-check.
            rec_result = engine.run_for_user(
                user_id,
                include_ai_narratives=False,
                finance_ctx=finance_ctx,
            )
            items_ranked = _items_ranked_from_engine_result(rec_result)

            # Cap remaining position changes by subtracting executed sells.
            sells_executed_count = len(sold_symbols)
            remaining_cap = max(0, DEFAULT_PARAMS.max_position_changes_per_rebalance - sells_executed_count)
            buy_params = RebalanceChurnParams(
                min_hold_days=DEFAULT_PARAMS.min_hold_days,
                confidence_min=DEFAULT_PARAMS.confidence_min,
                delta_strength_min=DEFAULT_PARAMS.delta_strength_min,
                n_keep=DEFAULT_PARAMS.n_keep,
                n_buy=DEFAULT_PARAMS.n_buy,
                max_sells_per_rebalance=DEFAULT_PARAMS.max_sells_per_rebalance,
                max_position_changes_per_rebalance=remaining_cap,
                sell_cooldown_days=DEFAULT_PARAMS.sell_cooldown_days,
                market_confidence_threshold=DEFAULT_PARAMS.market_confidence_threshold,
            )
            planner = RebalancePlanner(buy_params)

            # Prevent additional sells during buy phase (cooldown).
            last_sell_completed_at = sess.get("sell_completed_at") or now_utc

            planned = planner.plan(
                now_utc=now_utc,
                trigger_type=f"{trigger_type}:buy_next_day",
                holdings_rows=holdings_after_sell,
                items_ranked=items_ranked,
                prev_session_payload=payload_json,
                last_sell_completed_at=last_sell_completed_at,
                force_scenario1=(scenario == "scenario1"),
                target_scenario=scenario if scenario in ("scenario1", "scenario2") else None,
                finance_ctx=finance_ctx,
            )

            buy_orders = planned.get("buy_orders") or []
            if not buy_orders:
                skipped += 1
                _db_mark_buy_done(session_id, completed_at=now_utc)
                continue

            asyncio.run(
                execution.execute_buy_phase(
                    user_id=user_id,
                    scenario=scenario,
                    rebalance_session_id=session_id,
                    why_lines=planned.get("why_lines") or [],
                    buy_orders=buy_orders,
                )
            )
            _db_mark_buy_done(session_id, completed_at=datetime.now(timezone.utc))
            executed_buys += 1
            processed += 1
        except Exception as e:
            logger.exception("rebalance_buy_job error session_id=%s: %s", session_id, e)
            errors.append({"session_id": session_id, "error": str(e)})

    return {
        "job_id": job_id,
        "processed": processed,
        "executed_buys": executed_buys,
        "skipped": skipped,
        "errors": errors,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    out = run_rebalance_buy_job(job_id="cli")
    print(out)
    sys.exit(0 if not out.get("errors") else 1)

