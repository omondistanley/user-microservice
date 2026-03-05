"""
Proxy /api/v1/* resources to expense and budget microservices.
Forward method, path, query, body, and selected headers (e.g. Authorization).
"""
import logging

import httpx
from fastapi import Request, Response
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger(__name__)

# Headers to forward from client to backend (lowercase)
FORWARD_HEADERS = {"authorization", "content-type", "idempotency-key", "x-request-id"}

# Headers to drop from backend response (hop-by-hop and connection-specific)
DROP_RESPONSE_HEADERS = {"transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"}


async def _read_body(request: Request) -> bytes:
    body = await request.body()
    return body


def _forward_headers(request: Request) -> dict[str, str]:
    out = {}
    for name in FORWARD_HEADERS:
        val = request.headers.get(name)
        if val is not None:
            out[name] = val
    if "x-request-id" not in out:
        rid = getattr(request.state, "request_id", None)
        if rid:
            out["x-request-id"] = str(rid)
    return out


def _filter_response_headers(headers: dict) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in DROP_RESPONSE_HEADERS}


async def proxy_request(
    request: Request,
    base_url: str,
    path_prefix: str,
    path_suffix: str,
) -> StarletteResponse:
    """Forward request to base_url + path_prefix + path_suffix + query."""
    if not base_url:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"detail": "Proxy not configured"})
    url = f"{base_url}{path_prefix}"
    if path_suffix:
        url = f"{url}/{path_suffix}"
    query = str(request.url.query)
    if query:
        url = f"{url}?{query}"
    headers = _forward_headers(request)
    body = await _read_body(request)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(
                request.method,
                url,
                headers=headers,
                content=body,
            )
    except Exception as e:
        rid = getattr(request.state, "request_id", None)
        logger.exception("Proxy request failed request_id=%s error=%s", rid, e)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"detail": "Bad gateway"})
    filtered_headers = _filter_response_headers(dict(resp.headers))
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=filtered_headers,
    )
