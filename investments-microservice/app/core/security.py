"""
JWT decode only. Investments service validates tokens issued by user-microservice.
"""
from typing import Any

from jose import jwt

from app.core.config import ALGORITHM, SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={"verify_aud": True, "verify_iss": True},
    )
