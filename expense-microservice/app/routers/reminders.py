"""Phase 7: Calendar reminders (ICS) — recurring due dates, budget review hints."""
from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordBearer

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["reminders"])
_bearer_optional = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


def _escape_ics(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


async def _resolve_calendar_user_id(
    token: Optional[str] = Query(None),
    bearer_token: Optional[str] = Depends(_bearer_optional),
) -> int:
    # Preferred path: bearer auth
    if bearer_token:
        from app.core.security import decode_token

        try:
            payload = decode_token(bearer_token)
            sub = payload.get("sub")
            if sub is not None:
                return int(sub)
        except Exception:
            pass

    # Calendar-app friendly path: query token validated by user service.
    if token:
        if not USER_SERVICE_INTERNAL_URL:
            raise HTTPException(status_code=401, detail="Calendar token auth unavailable")
        headers = {}
        if INTERNAL_API_KEY:
            headers["x-internal-api-key"] = INTERNAL_API_KEY
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{USER_SERVICE_INTERNAL_URL}/internal/v1/calendar/subscription/{token}",
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                sub = data.get("user_id")
                if sub is not None:
                    return int(sub)
    raise HTTPException(status_code=401, detail="Could not validate credentials")


@router.get("/reminders/calendar.ics", response_class=PlainTextResponse)
async def calendar_ics(
    user_id: int = Depends(_resolve_calendar_user_id),
    days_ahead: int = Query(90, ge=1, le=365),
):
    """ICS feed for recurring due dates and reminder events. Subscribe via this URL (with auth)."""
    ds = _get_data_service()
    conn = ds._conn_autocommit()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT recurring_id, user_id, amount, currency, category_name, description, next_due_date
            FROM expenses_db.recurring_expense
            WHERE user_id = %s AND is_active = true
              AND next_due_date <= (CURRENT_DATE + %s::int)
              AND next_due_date >= CURRENT_DATE - 7
            ORDER BY next_due_date
            LIMIT 200
            """,
            (user_id, days_ahead),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Expense Tracker//Reminders//EN",
        "CALSCALE:GREGORIAN",
    ]
    for r in rows:
        dt = r["next_due_date"]
        if hasattr(dt, "isoformat"):
            dt_str = dt.isoformat().replace("-", "")
        else:
            dt_str = str(dt).replace("-", "")
        summary = "Recurring: %s" % (_escape_ics(r.get("category_name") or "Expense"))
        desc = _escape_ics(r.get("description") or "")
        if r.get("amount") is not None:
            desc = "Amount: %s %s. %s" % (r["amount"], r.get("currency") or "USD", desc)
        uid = "recurring-%s-%s@expense" % (r["recurring_id"], dt_str)
        lines.extend([
            "BEGIN:VEVENT",
            "UID:%s" % uid,
            "DTSTART;VALUE=DATE:%s" % dt_str,
            "DTEND;VALUE=DATE:%s" % dt_str,
            "SUMMARY:%s" % summary,
            "DESCRIPTION:%s" % desc,
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines)
    return PlainTextResponse(content=body, media_type="text/calendar")
