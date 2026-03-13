from datetime import date
import csv
import io
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user_id
from app.core.rate_limit import rate_limit_dep
from app.core.config import RATE_LIMIT_EXPENSES_PER_MINUTE
from app.models.expenses import (
    BalanceHistoryResponse,
    BalanceResponse,
    ExpenseCreate,
    ExpenseListParams,
    ExpenseResponse,
    SummaryResponse,
    ExpenseUpdate,
)
from app.resources.expense_resource import ExpenseResource
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["expenses"])


def _get_expense_resource() -> ExpenseResource:
    res = ServiceFactory.get_service("ExpenseResource")
    if res is None:
        raise RuntimeError("ExpenseResource not available")
    return res


def _get_expense_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.post("/expenses", response_model=ExpenseResponse)
async def create_expense(
    request: Request,
    payload: ExpenseCreate,
    user_id: int = Depends(get_current_user_id),
    _: None = Depends(rate_limit_dep(RATE_LIMIT_EXPENSES_PER_MINUTE)),
):
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key and idempotency_key.strip():
        key = idempotency_key.strip()
        ds = ServiceFactory.get_service("ExpenseDataService")
        if isinstance(ds, ExpenseDataService):
            existing_id = ds.get_idempotent_expense_id(user_id, key)
            if existing_id:
                from uuid import UUID
                resource = _get_expense_resource()
                try:
                    return resource.get_by_id(UUID(existing_id), user_id)
                except Exception:
                    pass
    resource = _get_expense_resource()
    response = resource.create(user_id, payload)
    if idempotency_key and idempotency_key.strip():
        ds = ServiceFactory.get_service("ExpenseDataService")
        if isinstance(ds, ExpenseDataService):
            ds.set_idempotency(user_id, idempotency_key.strip(), str(response.expense_id))
    return response


@router.get("/expenses", response_model=dict)
async def list_expenses(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    category_code: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    tag_id: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    min_amount: Optional[Decimal] = Query(None),
    max_amount: Optional[Decimal] = Query(None),
    household_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if tag_id:
        try:
            UUID(tag_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tag id")
    hh_uuid = None
    if household_id:
        try:
            hh_uuid = UUID(household_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid household_id")
    resource = _get_expense_resource()
    params = ExpenseListParams(
        date_from=date_from,
        date_to=date_to,
        category_code=category_code,
        category=category,
        tag_id=tag_id,
        tag=tag,
        min_amount=min_amount,
        max_amount=max_amount,
        household_id=hh_uuid,
        page=page,
        page_size=page_size,
    )
    items, total = resource.list(user_id, params)
    return {"items": items, "total": total}


@router.get("/expenses/export")
async def export_expenses(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    convert_to: Optional[str] = Query(None, min_length=3, max_length=3),
):
    ds = _get_expense_data_service()
    rows = ds.list_expenses_for_export(
        user_id=user_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
    )
    if convert_to:
        rows = ds.enrich_expense_export_rows_with_conversion(
            rows=rows,
            convert_to=convert_to,
            as_of_date=date_to or date.today(),
        )
    if format == "json":
        return {"items": rows, "total": len(rows)}

    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "expense_id",
        "user_id",
        "amount",
        "date",
        "currency",
        "category_code",
        "category_name",
        "description",
        "source",
        "plaid_transaction_id",
        "created_at",
        "updated_at",
    ]
    if convert_to:
        headers.extend(
            [
                "original_currency",
                "converted_currency",
                "converted_amount",
                "conversion_rate_date",
                "conversion_source",
            ]
        )
    writer.writerow(headers)
    for row in rows:
        base_values = [
            row.get("expense_id"),
            row.get("user_id"),
            row.get("amount"),
            row.get("date"),
            row.get("currency"),
            row.get("category_code"),
            row.get("category_name"),
            row.get("description"),
            row.get("source"),
            row.get("plaid_transaction_id"),
            row.get("created_at"),
            row.get("updated_at"),
        ]
        if convert_to:
            base_values.extend(
                [
                    row.get("original_currency"),
                    row.get("converted_currency"),
                    row.get("converted_amount"),
                    row.get("conversion_rate_date"),
                    row.get("conversion_source"),
                ]
            )
        writer.writerow(base_values)
    data = output.getvalue()
    filename = "expenses_export.csv"
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/expenses/balance/history", response_model=BalanceHistoryResponse)
async def get_balance_history(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    group_by: str = Query("week", description="'day' or 'week'"),
):
    if not date_from or not date_to:
        return BalanceHistoryResponse(items=[])
    resource = _get_expense_resource()
    return resource.get_balance_history(
        user_id,
        date_from.isoformat(),
        date_to.isoformat(),
        group_by=group_by,
    )


@router.get("/expenses/balance", response_model=BalanceResponse)
async def get_balance(
    user_id: int = Depends(get_current_user_id),
    as_of_date: Optional[date] = Query(None),
):
    resource = _get_expense_resource()
    as_of = as_of_date.isoformat() if as_of_date else None
    balance = resource.get_current_balance(user_id, as_of)
    return BalanceResponse(balance_after=balance)


@router.get("/expenses/summary", response_model=dict)
async def get_expense_summary(
    user_id: int = Depends(get_current_user_id),
    group_by: str = Query(..., description="'category' or 'month'"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    convert_to: Optional[str] = Query(None, min_length=3, max_length=3),
):
    if group_by not in ("category", "month"):
        raise HTTPException(status_code=400, detail="group_by must be 'category' or 'month'")
    if not convert_to:
        resource = _get_expense_resource()
        date_from_str = date_from.isoformat() if date_from else None
        date_to_str = date_to.isoformat() if date_to else None
        summary = resource.get_summary(user_id, group_by, date_from_str, date_to_str)
        return summary.model_dump()

    ds = _get_expense_data_service()
    date_from_str = date_from.isoformat() if date_from else None
    date_to_str = date_to.isoformat() if date_to else None
    rows = ds.get_expense_summary_by_currency(user_id, group_by, date_from_str, date_to_str)
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
            {
                "currency": from_currency,
                "total_amount": total_amount,
            }
        )
        rate_dates.add(str(converted["rate_date"]))
        if converted.get("source"):
            sources.add(str(converted["source"]))

    items = list(grouped.values())
    if group_by == "category":
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


@router.get("/expenses/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: str,
    user_id: int = Depends(get_current_user_id),
):
    from uuid import UUID
    try:
        eid = UUID(expense_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid expense id")
    resource = _get_expense_resource()
    return resource.get_by_id(eid, user_id)


@router.patch("/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    user_id: int = Depends(get_current_user_id),
):
    from uuid import UUID
    from fastapi import HTTPException
    try:
        eid = UUID(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense id")
    resource = _get_expense_resource()
    return resource.update(eid, user_id, payload)


@router.delete("/expenses/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: str,
    user_id: int = Depends(get_current_user_id),
):
    from uuid import UUID
    from fastapi import HTTPException
    try:
        eid = UUID(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense id")
    resource = _get_expense_resource()
    resource.delete(eid, user_id)
