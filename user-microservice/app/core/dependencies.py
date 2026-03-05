"""
FastAPI dependencies for auth: OAuth2 Bearer token and get_current_user.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.core.security import decode_token
from app.services.service_factory import ServiceFactory

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=True)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    data_service = ServiceFactory.get_service("UserResourceDataService")
    if data_service is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    # Load user by id (sub is user id as string)
    row = data_service.get_data_object(
        "users_db", "user", key_field="id", key_value=int(sub)
    )
    if row is None:
        raise credentials_exception
    return {"id": row["id"], "email": row["email"]}
