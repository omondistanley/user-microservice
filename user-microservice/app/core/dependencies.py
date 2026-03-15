"""
FastAPI dependencies for auth: OAuth2 Bearer token and get_current_user.
When X-User-Id header is present (set by API gateway after JWT validation), use it; else decode Bearer token.
"""
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.core.security import decode_token
from app.services.service_factory import ServiceFactory

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _load_user_by_id(user_id: int) -> dict | None:
    """Return {id, email} for user_id or None if not found."""
    data_service = ServiceFactory.get_service("UserResourceDataService")
    if data_service is None:
        return None
    row = data_service.get_data_object(
        "users_db", "user", key_field="id", key_value=user_id
    )
    if row is None:
        return None
    return {"id": row["id"], "email": row["email"]}


def get_current_user(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    token: str | None = Depends(oauth2_scheme),
):
    # When behind API gateway: trust X-User-Id set by gateway after JWT validation
    if x_user_id is not None and x_user_id.strip():
        try:
            user_id = int(x_user_id.strip())
            user = _load_user_by_id(user_id)
            if user is not None:
                return user
        except ValueError:
            pass
    # Direct access or no gateway: require Bearer token
    if not token:
        raise credentials_exception
    try:
        payload = decode_token(token)
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception
    user = _load_user_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user
