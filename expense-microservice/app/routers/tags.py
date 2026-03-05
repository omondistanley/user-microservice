from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user_id
from app.models.expenses import TagCreate, TagResponse
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["tags"])


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.get("/tags", response_model=list[TagResponse])
async def list_tags(user_id: int = Depends(get_current_user_id)):
    ds = _get_data_service()
    return ds.list_tags(user_id)


@router.post("/tags", response_model=TagResponse)
async def create_tag(payload: TagCreate, user_id: int = Depends(get_current_user_id)):
    ds = _get_data_service()
    try:
        return ds.create_tag(user_id, payload.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=409, detail="Tag already exists")


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: str, user_id: int = Depends(get_current_user_id)):
    ds = _get_data_service()
    try:
        tid = UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tag id")
    if not ds.delete_tag(user_id, str(tid)):
        raise HTTPException(status_code=404, detail="Tag not found")
