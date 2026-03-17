"""
FastAPI dependencies for auth: JWT decode or trusted X-User-Id from gateway.
When X-User-Id header is present (set by API gateway after JWT validation), use it; else decode Bearer token.
"""
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.security import decode_token

http_bearer = HTTPBearer(auto_error=False)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user_id(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> int:
    if x_user_id is not None and x_user_id.strip():
        try:
            return int(x_user_id.strip())
        except ValueError:
            pass
    if not credentials:
        raise credentials_exception
    try:
        payload = decode_token(credentials.credentials)
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        return int(sub)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception


def get_current_user(user_id: int = Depends(get_current_user_id)) -> dict:
    """Return dict with id for routes that expect user object."""
    return {"id": user_id}
