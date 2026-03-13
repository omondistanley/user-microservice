"""
Phase 3: CSV expense import (dry-run + commit).
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.core.dependencies import get_current_user_id
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["expense-import"])

CATEGORY_NAME_TO_CODE = {
    "food": 1, "transportation": 2, "transport": 2, "travel": 3, "utilities": 4,
    "entertainment": 5, "health": 6, "shopping": 7, "other": 8,
}


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


def _merge_preset_headers(headers_lower: dict[str, str], preset: Optional[str]) -> dict[str, str]:
    merged = dict(headers_lower)
    p = (preset or "").strip().lower()
    if p == "plaid":
        merged.setdefault("date", headers_lower.get("date", headers_lower.get("authorized date", "authorized date")))
        merged.setdefault("amount", headers_lower.get("amount", headers_lower.get("amount")))
        merged.setdefault("description", headers_lower.get("description", headers_lower.get("name", "name")))
        merged.setdefault("category", headers_lower.get("category", headers_lower.get("category")))
    elif p == "teller":
        merged.setdefault("date", headers_lower.get("date", headers_lower.get("date")))
        merged.setdefault("amount", headers_lower.get("amount", headers_lower.get("amount")))
        merged.setdefault("description", headers_lower.get("description", headers_lower.get("description", "description")))
        merged.setdefault("category", headers_lower.get("category", headers_lower.get("type", "type")))
    return merged


def _notify_import_commit(user_id: int, job_id: str, counts: dict) -> None:
    if not USER_SERVICE_INTERNAL_URL:
        return
    headers = {}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    payload = {
        "user_id": user_id,
        "type": "expense_import_committed",
        "title": "CSV import completed",
        "body": (
            f"Imported {counts.get('inserted_rows', 0)} expense rows "
            f"({counts.get('invalid_rows', 0)} invalid, {counts.get('duplicate_rows', 0)} duplicates)."
        ),
        "payload": {
            "job_id": job_id,
            "counts": counts,
        },
    }
    with httpx.Client(timeout=10.0) as client:
        # Best-effort notification so import commit result is not blocked by notification outages.
        client.post(
            f"{USER_SERVICE_INTERNAL_URL}/internal/v1/notifications",
            json=payload,
            headers=headers,
        )


def _normalize_description(s: Optional[str]) -> str:
    if not s or not str(s).strip():
        return ""
    return str(s).strip().lower()[:500]


def _parse_date(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    return None


def _parse_amount(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _resolve_category_from_str(name: Optional[str]) -> tuple[int, str]:
    if not name or not str(name).strip():
        return (8, "Other")
    key = str(name).strip().lower()
    code = CATEGORY_NAME_TO_CODE.get(key, 8)
    names = {1: "Food", 2: "Transportation", 3: "Travel", 4: "Utilities", 5: "Entertainment", 6: "Health", 7: "Shopping", 8: "Other"}
    return (code, names.get(code, "Other"))


def _row_to_normalized(row: dict, headers_lower: dict) -> tuple[Optional[dict], Optional[str]]:
    """Map row dict (keys may be various) to normalized_payload. Returns (normalized, validation_error)."""
    date_val = None
    for k in ("date", "transaction date", "transaction_date"):
        if k in headers_lower and row.get(headers_lower[k]) is not None:
            date_val = _parse_date(row.get(headers_lower[k]))
            if date_val:
                break
    if not date_val:
        return None, "Missing or invalid date"

    amount_val = None
    for k in ("amount", "total", "sum", "value"):
        if k in headers_lower and row.get(headers_lower[k]) is not None:
            amount_val = _parse_amount(row.get(headers_lower[k]))
            if amount_val is not None and amount_val >= 0:
                break
    if amount_val is None or amount_val < 0:
        return None, "Missing or invalid amount"

    cat_name = None
    for k in ("category", "category name", "category_name", "type"):
        if k in headers_lower and row.get(headers_lower[k]) is not None:
            cat_name = str(row.get(headers_lower[k], "")).strip() or None
            break
    category_code, category_name = _resolve_category_from_str(cat_name)

    currency = "USD"
    for k in ("currency", "curr", "ccy"):
        if k in headers_lower and row.get(headers_lower[k]) is not None:
            c = str(row.get(headers_lower[k], "")).strip().upper()
            if len(c) == 3:
                currency = c
            break

    description = None
    for k in ("description", "memo", "note", "details", "merchant"):
        if k in headers_lower and row.get(headers_lower[k]) is not None:
            description = str(row.get(headers_lower[k], "")).strip() or None
            break

    normalized = {
        "date": date_val,
        "amount": float(amount_val),
        "category_code": category_code,
        "category_name": category_name,
        "currency": currency,
        "description": (description or "")[:2000],
    }
    return normalized, None


@router.post("/expenses/import")
async def upload_import(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    preset: Optional[str] = Query(None, pattern="^(plaid|teller|generic)?$"),
    household_id: Optional[str] = Query(None),
    user_id: int = Depends(get_current_user_id),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    headers_lower = {str(f).strip().lower(): str(f).strip() for f in fieldnames}
    headers_lower = _merge_preset_headers(headers_lower, preset)
    ds = _get_data_service()
    job = ds.create_import_job(user_id, household_id if household_id else None, file.filename or "import.csv")
    job_id = str(job["job_id"])
    row_number = 0
    for row in reader:
        row_number += 1
        raw = dict(row)
        normalized, validation_error = _row_to_normalized(row, headers_lower)
        is_dup = False
        if normalized and not validation_error:
            desc_norm = _normalize_description(normalized.get("description"))
            is_dup = ds.expense_exists_duplicate(
                user_id,
                household_id if household_id else None,
                normalized["date"],
                Decimal(str(normalized["amount"])),
                desc_norm if desc_norm else None,
            )
        ds.add_import_row(
            job_id,
            row_number,
            raw,
            normalized,
            validation_error,
            is_dup,
        )
    ds.update_import_job_status(job_id, user_id, "validated")
    return {"job_id": job_id, "dry_run": dry_run, "total_rows": row_number, "preset": preset or "generic"}


@router.get("/expenses/import/{job_id}")
async def get_import_job(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    job = ds.get_import_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    rows = ds.get_import_rows(job_id)
    return {
        "job_id": job_id,
        "user_id": job["user_id"],
        "household_id": str(job["household_id"]) if job.get("household_id") else None,
        "filename": job["filename"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "rows": [
            {
                "row_number": r["row_number"],
                "raw_payload": r.get("raw_payload"),
                "normalized_payload": r.get("normalized_payload"),
                "validation_error": r.get("validation_error"),
                "is_duplicate": r.get("is_duplicate", False),
            }
            for r in rows
        ],
    }


@router.post("/expenses/import/{job_id}/commit")
async def commit_import(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id")
    ds = _get_data_service()
    try:
        counts = ds.commit_import_job(job_id, user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    _notify_import_commit(user_id=user_id, job_id=job_id, counts=counts)
    return counts


@router.post("/import/portable")
async def import_portable_json(
    payload: dict[str, Any],
    dry_run: bool = Query(True),
    household_id: Optional[str] = Query(None),
    user_id: int = Depends(get_current_user_id),
):
    """Import normalized portable JSON bundle into an import job."""
    schema_version = str(payload.get("schema_version") or "")
    if not schema_version:
        raise HTTPException(status_code=400, detail="schema_version is required")
    rows = payload.get("expenses")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="expenses array is required")
    ds = _get_data_service()
    job = ds.create_import_job(user_id, household_id if household_id else None, f"portable-{schema_version}.json")
    job_id = str(job["job_id"])
    row_number = 0
    for src in rows:
        if not isinstance(src, dict):
            continue
        row_number += 1
        normalized = {
            "date": src.get("date"),
            "amount": src.get("amount"),
            "category_code": src.get("category_code") or 8,
            "category_name": src.get("category_name") or "Other",
            "currency": (src.get("currency") or "USD"),
            "description": (src.get("description") or "")[:2000],
        }
        validation_error = None
        if not normalized["date"] or normalized["amount"] is None:
            validation_error = "Missing or invalid date/amount"
        is_dup = False
        if not validation_error:
            is_dup = ds.expense_exists_duplicate(
                user_id,
                household_id if household_id else None,
                str(normalized["date"]),
                Decimal(str(normalized["amount"])),
                _normalize_description(normalized.get("description")),
            )
        ds.add_import_row(
            job_id=job_id,
            row_number=row_number,
            raw_payload=src,
            normalized_payload=normalized,
            validation_error=validation_error,
            is_duplicate=is_dup,
        )
    ds.update_import_job_status(job_id, user_id, "validated")
    if not dry_run:
        counts = ds.commit_import_job(job_id, user_id)
        _notify_import_commit(user_id=user_id, job_id=job_id, counts=counts)
        return {"job_id": job_id, "dry_run": False, "counts": counts}
    return {"job_id": job_id, "dry_run": True, "total_rows": row_number}
