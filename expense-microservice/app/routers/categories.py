from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user_id
from app.models.categories import CategoryCreate, CategoryResponse
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["categories"])


def _get_data_service():
    ds = ServiceFactory.get_service("ExpenseDataService")
    if ds is None:
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(user_id: int = Depends(get_current_user_id)):
    ds = _get_data_service()
    rows = ds.get_categories()
    return [CategoryResponse(category_code=r["category_code"], name=r["name"]) for r in rows]


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    payload: CategoryCreate,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    try:
        row = ds.insert_category(name)
        if not row:
            raise HTTPException(status_code=409, detail="A category with this name already exists")
        return CategoryResponse(category_code=row["category_code"], name=row["name"])
    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "duplicate" in err:
            raise HTTPException(status_code=409, detail="A category with this name already exists")
        raise HTTPException(status_code=400, detail=str(e))
