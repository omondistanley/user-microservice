"""
Phase 3: Households API and internal scope endpoint.
All routes require JWT. Internal /internal/v1 scope endpoint optional x-internal-api-key.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.config import INTERNAL_API_KEY
from app.core.dependencies import get_current_user
from app.models.users import (
    ActiveHouseholdUpdate,
    HouseholdCreate,
    HouseholdMemberInvite,
    HouseholdMemberResponse,
    HouseholdMemberUpdate,
    HouseholdResponse,
    UserScopeResponse,
)
from app.services.household_service import (
    add_member,
    create_household,
    get_household,
    get_user_scope,
    is_active_member,
    list_households_for_user,
    list_members,
    remove_member,
    set_active_household,
    update_member,
)
from app.services.service_factory import ServiceFactory

router = APIRouter()


def _user_id(current_user: dict) -> int:
    return int(current_user["id"])


def _resolve_email_to_user_id(email: str) -> int | None:
    data_svc = ServiceFactory.get_service("UserResourceDataService")
    if not data_svc:
        return None
    row = data_svc.get_data_object("users_db", "user", key_field="email", key_value=email)
    return int(row["id"]) if row else None


# --- Public API (JWT required) ---

@router.post("/api/v1/households", tags=["households"], response_model=HouseholdResponse)
async def post_household(
    payload: HouseholdCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = _user_id(current_user)
    row = create_household(owner_user_id=user_id, name=payload.name)
    return HouseholdResponse(
        household_id=row["household_id"],
        owner_user_id=row["owner_user_id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        role="owner",
        status="active",
    )


@router.get("/api/v1/households", tags=["households"], response_model=list[HouseholdResponse])
async def list_households(current_user: dict = Depends(get_current_user)):
    user_id = _user_id(current_user)
    rows = list_households_for_user(user_id)
    return [
        HouseholdResponse(
            household_id=r["household_id"],
            owner_user_id=r["owner_user_id"],
            name=r["name"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            role=r.get("role"),
            status=r.get("status"),
        )
        for r in rows
    ]


@router.get("/api/v1/households/{household_id}", tags=["households"], response_model=HouseholdResponse)
async def get_household_by_id(
    household_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = _user_id(current_user)
    row = get_household(household_id, user_id)
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this household")
    return HouseholdResponse(
        household_id=row["household_id"],
        owner_user_id=row["owner_user_id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        role=row.get("role"),
        status=row.get("status"),
    )


@router.get(
    "/api/v1/households/{household_id}/members",
    tags=["households"],
    response_model=list[HouseholdMemberResponse],
)
async def get_household_members(
    household_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = _user_id(current_user)
    try:
        rows = list_members(household_id, user_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not a member of this household")
    return [
        HouseholdMemberResponse(
            household_id=r["household_id"],
            user_id=r["user_id"],
            role=r["role"],
            status=r["status"],
            invited_by_user_id=r.get("invited_by_user_id"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.post(
    "/api/v1/households/{household_id}/members",
    tags=["households"],
    response_model=HouseholdMemberResponse,
)
async def post_household_member(
    household_id: str,
    payload: HouseholdMemberInvite,
    current_user: dict = Depends(get_current_user),
):
    user_id = _user_id(current_user)
    invited_user_id = _resolve_email_to_user_id(payload.email)
    if invited_user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        row = add_member(household_id, invited_user_id, user_id, role=payload.role)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return HouseholdMemberResponse(
        household_id=row["household_id"],
        user_id=row["user_id"],
        role=row["role"],
        status=row["status"],
        invited_by_user_id=user_id,
        created_at=row["created_at"],
        updated_at=row.get("updated_at", row["created_at"]),
    )


@router.patch(
    "/api/v1/households/{household_id}/members/{member_user_id}",
    tags=["households"],
    response_model=HouseholdMemberResponse,
)
async def patch_household_member(
    household_id: str,
    member_user_id: int,
    payload: HouseholdMemberUpdate,
    current_user: dict = Depends(get_current_user),
):
    actor_id = _user_id(current_user)
    try:
        row = update_member(household_id, member_user_id, actor_id, role=payload.role, status=payload.status)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not row:
        raise HTTPException(status_code=404, detail="Member not found")
    return HouseholdMemberResponse(
        household_id=row["household_id"],
        user_id=row["user_id"],
        role=row["role"],
        status=row["status"],
        invited_by_user_id=None,
        created_at=row.get("created_at"),
        updated_at=row["updated_at"],
    )


@router.delete(
    "/api/v1/households/{household_id}/members/{member_user_id}",
    tags=["households"],
    status_code=204,
)
async def delete_household_member(
    household_id: str,
    member_user_id: int,
    current_user: dict = Depends(get_current_user),
):
    actor_id = _user_id(current_user)
    try:
        ok = remove_member(household_id, member_user_id, actor_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
    return None


# --- Internal: scope for expense/budget (optional x-internal-api-key) ---

def _validate_internal_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@router.get(
    "/internal/v1/users/me/scope",
    tags=["internal"],
    response_model=UserScopeResponse,
    include_in_schema=False,
)
async def get_my_scope(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(_validate_internal_key),
):
    user_id = _user_id(current_user)
    scope = get_user_scope(user_id)
    return UserScopeResponse(
        user_id=scope["user_id"],
        active_household_id=UUID(scope["active_household_id"]) if scope.get("active_household_id") else None,
    )


@router.get(
    "/internal/v1/households/{household_id}/members/check",
    tags=["internal"],
    include_in_schema=False,
)
async def check_household_member(
    household_id: str,
    user_id: int = Query(..., description="User ID to check membership for"),
    _: None = Depends(_validate_internal_key),
):
    """Returns 200 if user_id is active member of household_id, 403 otherwise. For expense/budget scope validation."""
    if is_active_member(household_id, user_id):
        return {"ok": True}
    raise HTTPException(status_code=403, detail="Not a member of this household")
