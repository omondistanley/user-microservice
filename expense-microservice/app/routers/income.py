from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.models.income import (
    CashflowSummaryResponse,
    IncomeCreate,
    IncomeResponse,
    IncomeSummaryItem,
    IncomeSummaryResponse,
    IncomeUpdate,
)
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["income"])


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.post("/income", response_model=IncomeResponse)
async def create_income(
    payload: IncomeCreate,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    now = datetime.now(timezone.utc)
    row = ds.create_income(
        {
            "user_id": user_id,
            "amount": payload.amount,
            "date": payload.date,
            "currency": (payload.currency or "USD").upper(),
            "income_type": payload.income_type,
            "source_label": payload.source_label,
            "description": payload.description,
            "created_at": now,
            "updated_at": now,
        }
    )
    return IncomeResponse(**row)


@router.get("/income", response_model=dict)
async def list_income(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    income_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    ds = _get_data_service()
    items, total = ds.list_income(
        user_id=user_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        income_type=income_type,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {"items": [IncomeResponse(**r) for r in items], "total": total}


@router.get("/income/summary", response_model=dict)
async def income_summary(
    user_id: int = Depends(get_current_user_id),
    group_by: str = Query("month", pattern="^(month|type)$"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    convert_to: Optional[str] = Query(None, min_length=3, max_length=3),
):
    ds = _get_data_service()
    date_from_str = date_from.isoformat() if date_from else None
    date_to_str = date_to.isoformat() if date_to else None
    if not convert_to:
        rows = ds.get_income_summary(
            user_id=user_id,
            group_by=group_by,
            date_from=date_from_str,
            date_to=date_to_str,
        )
        items = [IncomeSummaryItem(**r) for r in rows]
        return IncomeSummaryResponse(group_by=group_by, items=items).model_dump()

    rows = ds.get_income_summary_by_currency(
        user_id=user_id,
        group_by=group_by,
        date_from=date_from_str,
        date_to=date_to_str,
    )
    convert_currency = str(convert_to).upper()
    as_of_date = date_to or date.today()
    grouped: dict[str, dict] = {}
    rate_dates: set[str] = set()
    sources: set[str] = set()

    for row in rows:
        total_amount = Decimal(str(row.get("total_amount") or "0"))
        from_currency = str(row.get("currency") or "USD").upper()
        converted = ds.convert_amount(total_amount, from_currency, convert_currency, as_of_date=as_of_date)
        if not converted:
            raise HTTPException(
                status_code=422,
                detail=f"Missing exchange rate for {from_currency}->{convert_currency}",
            )
        key = str(row["group_key"])
        if key not in grouped:
            grouped[key] = {
                "group_key": key,
                "label": row["label"],
                "total_amount": Decimal("0"),
                "count": 0,
                "original_totals": [],
                "converted_currency": convert_currency,
            }
        grouped[key]["total_amount"] += Decimal(str(converted["converted_amount"]))
        grouped[key]["count"] += int(row.get("count") or 0)
        grouped[key]["original_totals"].append(
            {"currency": from_currency, "total_amount": total_amount}
        )
        rate_dates.add(str(converted["rate_date"]))
        if converted.get("source"):
            sources.add(str(converted["source"]))

    items = list(grouped.values())
    if group_by == "type":
        items.sort(key=lambda x: Decimal(str(x["total_amount"])), reverse=True)
    else:
        items.sort(key=lambda x: str(x["group_key"]), reverse=True)

    conversion_meta = {
        "currency": convert_currency,
        "rate_date": sorted(rate_dates)[-1] if rate_dates else None,
        "source": sorted(sources)[0] if sources else None,
    }
    return {
        "group_by": group_by,
        "items": items,
        "convert_to": convert_currency,
        "conversion": conversion_meta,
    }


@router.get("/cashflow/summary", response_model=dict)
async def cashflow_summary(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    convert_to: Optional[str] = Query(None, min_length=3, max_length=3),
):
    ds = _get_data_service()
    date_from_str = date_from.isoformat() if date_from else None
    date_to_str = date_to.isoformat() if date_to else None
    if not convert_to:
        income_total = ds.get_income_total(
            user_id=user_id,
            date_from=date_from_str,
            date_to=date_to_str,
        )
        expense_total = ds.get_expense_total(
            user_id=user_id,
            date_from=date_from_str,
            date_to=date_to_str,
        )
        return CashflowSummaryResponse(
            income_total=income_total,
            expense_total=expense_total,
            savings=income_total - expense_total,
        ).model_dump()

    convert_currency = str(convert_to).upper()
    as_of_date = date_to or date.today()
    income_by_currency = ds.get_income_totals_by_currency(
        user_id=user_id,
        date_from=date_from_str,
        date_to=date_to_str,
    )
    expense_by_currency = ds.get_expense_totals_by_currency(
        user_id=user_id,
        date_from=date_from_str,
        date_to=date_to_str,
    )

    converted_income_total = Decimal("0")
    converted_expense_total = Decimal("0")
    rate_dates: set[str] = set()
    sources: set[str] = set()

    for row in income_by_currency:
        total_amount = Decimal(str(row.get("total_amount") or "0"))
        from_currency = str(row.get("currency") or "USD").upper()
        converted = ds.convert_amount(total_amount, from_currency, convert_currency, as_of_date=as_of_date)
        if not converted:
            raise HTTPException(
                status_code=422,
                detail=f"Missing exchange rate for {from_currency}->{convert_currency}",
            )
        converted_income_total += Decimal(str(converted["converted_amount"]))
        rate_dates.add(str(converted["rate_date"]))
        if converted.get("source"):
            sources.add(str(converted["source"]))

    for row in expense_by_currency:
        total_amount = Decimal(str(row.get("total_amount") or "0"))
        from_currency = str(row.get("currency") or "USD").upper()
        converted = ds.convert_amount(total_amount, from_currency, convert_currency, as_of_date=as_of_date)
        if not converted:
            raise HTTPException(
                status_code=422,
                detail=f"Missing exchange rate for {from_currency}->{convert_currency}",
            )
        converted_expense_total += Decimal(str(converted["converted_amount"]))
        rate_dates.add(str(converted["rate_date"]))
        if converted.get("source"):
            sources.add(str(converted["source"]))

    original_income_total = sum((Decimal(str(r.get("total_amount") or "0")) for r in income_by_currency), Decimal("0"))
    original_expense_total = sum((Decimal(str(r.get("total_amount") or "0")) for r in expense_by_currency), Decimal("0"))

    return {
        "income_total": converted_income_total,
        "expense_total": converted_expense_total,
        "savings": converted_income_total - converted_expense_total,
        "convert_to": convert_currency,
        "conversion": {
            "currency": convert_currency,
            "rate_date": sorted(rate_dates)[-1] if rate_dates else None,
            "source": sorted(sources)[0] if sources else None,
        },
        "original_income_total": original_income_total,
        "original_expense_total": original_expense_total,
        "original_savings": original_income_total - original_expense_total,
        "income_currency_breakdown": income_by_currency,
        "expense_currency_breakdown": expense_by_currency,
    }


@router.get("/income/{income_id}", response_model=IncomeResponse)
async def get_income(
    income_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(income_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid income id")
    ds = _get_data_service()
    row = ds.get_income_by_id(income_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Income not found")
    return IncomeResponse(**row)


@router.patch("/income/{income_id}", response_model=IncomeResponse)
async def update_income(
    income_id: str,
    payload: IncomeUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(income_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid income id")
    ds = _get_data_service()
    updates = payload.model_dump(exclude_unset=True)
    if "currency" in updates and updates["currency"]:
        updates["currency"] = str(updates["currency"]).upper()
    updates["updated_at"] = datetime.now(timezone.utc)
    row = ds.update_income(income_id, user_id, updates)
    if not row:
        raise HTTPException(status_code=404, detail="Income not found")
    return IncomeResponse(**row)


@router.delete("/income/{income_id}", status_code=204)
async def delete_income(
    income_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(income_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid income id")
    ds = _get_data_service()
    if not ds.soft_delete_income(income_id, user_id):
        raise HTTPException(status_code=404, detail="Income not found")
