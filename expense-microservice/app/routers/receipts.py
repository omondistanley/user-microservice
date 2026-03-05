from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.core.dependencies import get_current_user_id
from app.models.receipts import ReceiptCreate, ReceiptResponse
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
        if isinstance(file, UploadFile) and file.filename:
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
