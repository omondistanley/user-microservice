from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.core.dependencies import get_current_user_id
from app.models.receipts import ReceiptCreate, ReceiptResponse
from app.services.receipt_ocr import is_tesseract_available, run_ocr
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["receipts"])


def _get_receipt_service():
    svc = ServiceFactory.get_service("ReceiptService")
    if svc is None:
        raise RuntimeError("ReceiptService not available")
    return svc


def _get_data_service():
    ds = ServiceFactory.get_service("ExpenseDataService")
    if ds is None:
        raise RuntimeError("ExpenseDataService not available")
    return ds


def _ensure_expense_exists(expense_id: str, user_id: int) -> None:
    try:
        eid = UUID(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense id")
    ds = _get_data_service()
    if not ds.get_expense_by_id(eid, user_id):
        raise HTTPException(status_code=404, detail="Expense not found")


@router.post("/expenses/{expense_id}/receipts", response_model=ReceiptResponse)
async def create_receipt(
    expense_id: str,
    request: Request,
    user_id: int = Depends(get_current_user_id),
):
    _ensure_expense_exists(expense_id, user_id)
    svc = _get_receipt_service()
    content_type_header = request.headers.get("content-type") or ""
    if "multipart/form-data" in content_type_header:
        form = await request.form()
        file: UploadFile | None = form.get("file")
        if file is not None and getattr(file, "filename", None):
            file_bytes = await file.read()
            file_name = form.get("file_name") or file.filename or "receipt"
            if isinstance(file_name, UploadFile):
                file_name = file_name.filename or "receipt"
            content_type = form.get("content_type") or file.content_type or "application/octet-stream"
            if isinstance(content_type, UploadFile):
                content_type = "application/octet-stream"
            row = svc.create_receipt(
                expense_id=expense_id,
                user_id=user_id,
                file_name=file_name,
                content_type=content_type,
                file_size_bytes=len(file_bytes),
                file_bytes=file_bytes,
            )
        else:
            file_name = form.get("file_name")
            content_type = form.get("content_type")
            file_size_bytes = form.get("file_size_bytes")
            storage_key = form.get("storage_key")
            if not all([file_name, content_type, file_size_bytes, storage_key]):
                raise HTTPException(
                    status_code=400,
                    detail="Multipart without file requires file_name, content_type, file_size_bytes, storage_key",
                )
            try:
                file_size_bytes = int(file_size_bytes)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="file_size_bytes must be integer")
            row = svc.create_receipt(
                expense_id=expense_id,
                user_id=user_id,
                file_name=str(file_name),
                content_type=str(content_type),
                file_size_bytes=file_size_bytes,
                storage_key=str(storage_key),
            )
    else:
        body = await request.json()
        payload = ReceiptCreate.model_validate(body)
        row = svc.create_receipt(
            expense_id=expense_id,
            user_id=user_id,
            file_name=payload.file_name,
            content_type=payload.content_type,
            file_size_bytes=payload.file_size_bytes,
            storage_key=payload.storage_key,
        )
    return ReceiptResponse(
        receipt_id=row["receipt_id"],
        expense_id=row["expense_id"],
        user_id=row["user_id"],
        file_name=row["file_name"],
        content_type=row["content_type"],
        file_size_bytes=row["file_size_bytes"],
        uploaded_at=row["uploaded_at"],
    )


@router.get("/expenses/{expense_id}/receipts", response_model=list[ReceiptResponse])
async def list_receipts(
    expense_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense id")
    ds = _get_data_service()
    rows = ds.get_receipts_by_expense(expense_id, user_id)
    return [
        ReceiptResponse(
            receipt_id=r["receipt_id"],
            expense_id=r["expense_id"],
            user_id=r["user_id"],
            file_name=r["file_name"],
            content_type=r["content_type"],
            file_size_bytes=r["file_size_bytes"],
            uploaded_at=r["uploaded_at"],
        )
        for r in rows
    ]


@router.get("/receipts/{receipt_id}/download")
async def download_receipt(
    receipt_id: str,
    user_id: int = Depends(get_current_user_id),
):
    svc = _get_receipt_service()
    try:
        data, content_type, file_name = svc.get_receipt_download(receipt_id, user_id)
    except HTTPException:
        raise
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.delete("/receipts/{receipt_id}", status_code=204)
async def delete_receipt(
    receipt_id: str,
    user_id: int = Depends(get_current_user_id),
):
    svc = _get_receipt_service()
    if not svc.delete_receipt(receipt_id, user_id):
        raise HTTPException(status_code=404, detail="Receipt not found")


@router.post("/receipts/{receipt_id}/ocr")
async def run_receipt_ocr(
    receipt_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """Run OCR on receipt image and store raw text + extracted fields. Requires tesseract-ocr."""
    try:
        UUID(receipt_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid receipt id")
    svc = _get_receipt_service()
    ds = _get_data_service()
    try:
        data, _, _ = svc.get_receipt_download(receipt_id, user_id)
    except HTTPException:
        raise
    raw_text, extracted = run_ocr(data)
    if raw_text is None and not extracted:
        raise HTTPException(status_code=503, detail="OCR unavailable (install tesseract-ocr) or no text detected")
    ds.insert_receipt_ocr_result(receipt_id, raw_text, extracted)
    result = ds.get_receipt_ocr_result(receipt_id, user_id)
    return {
        "receipt_id": receipt_id,
        "raw_text": result.get("raw_text"),
        "extracted": result.get("extracted_json") or {},
        "ocr_run_at": result.get("ocr_run_at"),
        "diagnostics": {
            "tesseract_available": is_tesseract_available(),
            "raw_text_length": len(result.get("raw_text") or ""),
        },
    }


@router.get("/receipts/{receipt_id}/ocr")
async def get_receipt_ocr(
    receipt_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """Return stored OCR result for a receipt."""
    try:
        UUID(receipt_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid receipt id")
    ds = _get_data_service()
    result = ds.get_receipt_ocr_result(receipt_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Receipt or OCR result not found")
    return {
        "receipt_id": str(result["receipt_id"]),
        "raw_text": result.get("raw_text"),
        "extracted": result.get("extracted_json") or {},
        "ocr_run_at": result.get("ocr_run_at"),
        "diagnostics": {
            "tesseract_available": is_tesseract_available(),
            "raw_text_length": len(result.get("raw_text") or ""),
        },
    }


@router.post("/receipts/{receipt_id}/apply-extraction")
async def apply_receipt_extraction(
    receipt_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """Apply extracted OCR fields (amount, date, description) to the linked expense."""
    try:
        UUID(receipt_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid receipt id")
    ds = _get_data_service()
    ocr = ds.get_receipt_ocr_result(receipt_id, user_id)
    if not ocr:
        raise HTTPException(status_code=404, detail="Run OCR first (POST /receipts/{id}/ocr)")
    receipt_row = ds.get_receipt_by_id(receipt_id, user_id)
    if not receipt_row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    expense_id = receipt_row["expense_id"]
    extracted = ocr.get("extracted_json") or {}
    updates = {}
    if "amount" in extracted and extracted["amount"] is not None:
        try:
            updates["amount"] = Decimal(str(extracted["amount"]))
        except Exception:
            pass
    if "date" in extracted and extracted["date"]:
        updates["date"] = extracted["date"]
    if "description" in extracted and extracted["description"]:
        updates["description"] = str(extracted["description"])[:2000]
    if not updates:
        return {"applied": False, "message": "No fields to apply", "expense_id": str(expense_id)}
    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(timezone.utc)
    ds.update_expense(UUID(str(expense_id)), user_id, updates)
    return {"applied": True, "expense_id": str(expense_id), "updated": list(updates.keys())}
