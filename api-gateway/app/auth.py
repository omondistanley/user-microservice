"""
JWT validation only. Returns payload dict or None.
"""
from typing import Any

from jose import JWTError, jwt

from app.config import ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, SECRET_KEY


def validate_jwt(token: str) -> dict[str, Any] | None:
    if not token or not token.strip():
        return None
    try:
        payload = jwt.decode(
            token.strip(),
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"verify_aud": True, "verify_iss": True},
        )
        return payload
    except JWTError:
        return None
