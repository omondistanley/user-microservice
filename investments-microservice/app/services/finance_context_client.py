"""
Fetch savings, goals, and optionally budget from expense (or gateway) for recommendation personalization.
Uses the user's JWT (Authorization header) so the expense service returns that user's data.
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import (
    EXPENSE_SERVICE_URL,
    FINANCE_CONTEXT_TIMEOUT_SECONDS,
    GATEWAY_PUBLIC_URL,
)

logger = logging.getLogger(__name__)


@dataclass
class FinanceContext:
    """Aggregated finance data for soft scoring and narrative."""

    savings_rate: Optional[float] = None  # (income - expense) / income over window
    surplus: Optional[float] = None  # income_total - expense_total
    income_total: Optional[float] = None
    expense_total: Optional[float] = None
    active_goals_count: int = 0
    goal_horizon_months: Optional[int] = None  # min months to nearest target_date
    goals_behind: bool = False  # any goal > 15% behind target
    goals_behind_count: int = 0
    budget_over: bool = False  # placeholder; set when budget summary is available
    data_fresh: bool = True  # False if no recent income/expense data


def _base_url() -> str:
    if GATEWAY_PUBLIC_URL:
        return GATEWAY_PUBLIC_URL
    if EXPENSE_SERVICE_URL:
        return EXPENSE_SERVICE_URL
    return ""


def fetch_finance_context(auth_header: Optional[str], window_months: int = 6) -> Optional[FinanceContext]:
    """
    Call expense (or gateway) for cashflow summary and goals. Returns None on failure or missing config.
    auth_header: e.g. "Bearer <jwt>"
    """
    base = _base_url()
    if not base or not auth_header:
        return None
    timeout = FINANCE_CONTEXT_TIMEOUT_SECONDS
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}

    ctx = FinanceContext()

    try:
        end = date.today()
        start = end - timedelta(days=min(365, window_months * 31))
        with httpx.Client(timeout=timeout) as client:
            # Cashflow summary
            r = client.get(
                f"{base}/api/v1/cashflow/summary",
                params={"date_from": start.isoformat(), "date_to": end.isoformat()},
                headers=headers,
            )
            if r.status_code == 200:
                data = r.json()
                income = float(data.get("income_total") or 0)
                expense = float(data.get("expense_total") or 0)
                ctx.income_total = income
                ctx.expense_total = expense
                ctx.surplus = income - expense
                if income and income > 0:
                    ctx.savings_rate = (income - expense) / income
                ctx.data_fresh = True
            else:
                ctx.data_fresh = False

            # Goals list
            r_goals = client.get(
                f"{base}/api/v1/goals",
                params={"active_only": "true", "page_size": 50},
                headers=headers,
            )
            if r_goals.status_code != 200:
                return ctx

            goals_data = r_goals.json()
            items: List[Dict[str, Any]] = goals_data.get("items") or []
            ctx.active_goals_count = len(items)

            if not items:
                return ctx

            min_months: Optional[int] = None
            behind_count = 0
            for g in items:
                target_date_str = g.get("target_date")
                if target_date_str:
                    try:
                        target = date.fromisoformat(target_date_str.replace("Z", "").split("T")[0])
                        delta = (target - end).days
                        months = max(0, delta // 30) if delta > 0 else 0
                        if min_months is None or months < min_months:
                            min_months = months
                    except (ValueError, TypeError):
                        pass
                # Progress: current vs target
                goal_id = g.get("goal_id")
                if goal_id:
                    r_prog = client.get(f"{base}/api/v1/goals/{goal_id}/progress", headers=headers)
                    if r_prog.status_code == 200:
                        prog = r_prog.json()
                        target_amt = float(prog.get("target_amount") or 0)
                        current_amt = float(prog.get("current_amount") or 0)
                        if target_amt > 0 and current_amt < target_amt * 0.85:
                            behind_count += 1

            ctx.goal_horizon_months = min_months
            ctx.goals_behind = behind_count > 0
            ctx.goals_behind_count = behind_count

    except Exception as e:
        logger.warning("finance_context_fetch_failed %s", e)
        return None

    return ctx
