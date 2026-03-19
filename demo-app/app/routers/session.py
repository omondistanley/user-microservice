"""POST /demo/session — passwordless demo session cookie."""
from fastapi import APIRouter, Request, Response

from app.auth_demo import COOKIE_NAME, issue_demo_token
from app.db import touch_activity
from app.limiter_util import limiter

router = APIRouter(tags=["demo-session"])


@router.post("/demo/session")
@limiter.limit("30/hour")
async def create_demo_session(request: Request, response: Response):
    token, _sid = issue_demo_token()
    secure = request.url.scheme == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=60 * 60 * 4,
        path="/",
    )
    touch_activity()
    return {"ok": True, "message": "Demo session started"}


@router.post("/demo/session/end")
async def end_demo_session(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
