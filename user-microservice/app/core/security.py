"""
Password hashing (bcrypt) and JWT create/decode for auth.
Uses bcrypt directly (no passlib) for compatibility with bcrypt 4.1+.
"""
from datetime import datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import ALGORITHM, SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ISSUER, JWT_AUDIENCE


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(sub: str, email: str, expire_minutes: int | None = None) -> str:
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in environment for JWT")
    now = datetime.utcnow()
    expire = now + timedelta(minutes=expire_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": sub,
        "email": email,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], audience=JWT_AUDIENCE)
