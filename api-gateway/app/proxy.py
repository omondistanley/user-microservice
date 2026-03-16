"""
Forward request to upstream. Sets X-User-Id; does not forward Authorization.
"""
import logging

import httpx
from fastapi.responses import JSONResponse
from fastapi import Request, Response
from starlette.responses import Response as StarletteResponse

from app.config import PROXY_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Forward from client (except Authorization - we use X-User-Id instead)
# x-webhook-secret: for Apple Wallet webhook; expense service validates it
FORWARD_HEADERS = {"content-type", "idempotency-key", "x-request-id", "x-webhook-secret"}

DROP_RESPONSE_HEADERS = {
    "transfer-encoding", "connection", "keep-alive",
    "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade",
}


def _build_headers(request: Request, request_id: str, user_id: int | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in FORWARD_HEADERS:
        val = request.headers.get(name)
        if val is not None:
            out[name] = val
    out["x-request-id"] = request_id
    if user_id is not None:
        out["x-user-id"] = str(user_id)
    return out


def _filter_response_headers(headers: dict) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in DROP_RESPONSE_HEADERS}


async def proxy_request(
    request: Request,
    upstream_base: str,
    path: str,
    query: str,
    user_id: int | None,
    request_id: str,
) -> StarletteResponse:
    url = f"{upstream_base}{path}"
    if query:
        url = f"{url}?{query}"
    headers = _build_headers(request, request_id, user_id)
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            resp = await client.request(
                request.method,
                url,
                headers=headers,
                content=body,
            )
    except Exception as e:
        logger.exception("proxy_request_failed request_id=%s error=%s", request_id, e)
        return JSONResponse(status_code=502, content={"detail": "Bad gateway"})
    filtered = _filter_response_headers(dict(resp.headers))
    return Response(content=resp.content, status_code=resp.status_code, headers=filtered)
