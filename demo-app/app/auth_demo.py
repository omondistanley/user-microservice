"""Demo-only JWT in httpOnly cookie."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from jose import JWTError, jwt

from app.config import DEMO_JWT_EXPIRE_MINUTES, DEMO_JWT_SECRET

ALGO = "HS256"
COOKIE_NAME = "demo_jwt"


def issue_demo_token() -> tuple[str, str]:
    sid = str(uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sid": sid,
        "demo": True,
        "iat": now,
        "exp": now + timedelta(minutes=DEMO_JWT_EXPIRE_MINUTES),
    }
    token = jwt.encode(payload, DEMO_JWT_SECRET, algorithm=ALGO)
    return token, sid


def verify_demo_token(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, DEMO_JWT_SECRET, algorithms=[ALGO])
        if not payload.get("demo") or not payload.get("sid"):
            return None
        return payload
    except JWTError:
        return None
