"""
API Gateway: JWT validation once, Redis rate limit, path-based routing, proxy with X-User-Id.
"""
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.auth import validate_jwt
from app.config import (
    GATEWAY_RATE_LIMIT_PER_IP,
    GATEWAY_RATE_LIMIT_PER_USER,
    REDIS_URL,
    get_cors_origins,
)
from app.proxy import proxy_request
from app.rate_limit import check_rate_limit
from app.routing import get_upstream

logger = logging.getLogger("gateway")

# Paths that do not require Bearer token (route to user service for HTML/auth)
# /auth: OAuth (Google, Apple) redirect and callback
# /api/v1/apple-wallet: webhook uses X-Webhook-Secret; expense service validates it
NO_JWT_PREFIXES = (
    "/health",
    "/ready",
    "/login",
    "/register",
    "/token",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/verify-email/",
    "/auth",
    "/static",
    "/api/v1/apple-wallet",
    # Plaid Hosted Link webhook (SESSION_FINISHED) must be unauthenticated
    "/api/v1/plaid/webhook",
)
NO_JWT_EXACT = {"/", "/health", "/ready"}


def _requires_jwt(path: str, method: str) -> bool:
    if path in NO_JWT_EXACT:
        return False
    # Public pre-auth endpoint used by Register flow (email validation)
    if path == "/api/v1/validate-email":
        return False
    # Gmail Pub/Sub push: verified by query token on expense service (POST only)
    if method.upper() == "POST" and path.rstrip("/") == "/api/v1/gmail/webhook":
        return False
    # Prefix allowlist must be checked before blanket /api/v1 JWT rule
    for p in NO_JWT_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return False
    if path.startswith("/api/v1/") or path.startswith("/internal/"):
        return True
    return False


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = None
    if REDIS_URL:
        try:
            redis = Redis.from_url(REDIS_URL, decode_responses=True)
            await redis.ping()
        except Exception as e:
            logger.warning("redis_connect_failed url=%s error=%s", REDIS_URL, e)
    app.state.redis = redis
    yield
    if redis:
        await redis.aclose()


app = FastAPI(title="API Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_and_logging(request: Request, call_next):
    request_id = (request.headers.get("x-request-id") or "").strip() or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 3)
    user_id = getattr(request.state, "user_id", None)
    log_payload = {
        "service": "gateway",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }
    if user_id is not None:
        log_payload["user_id"] = user_id
    logger.info(json.dumps(log_payload, default=str))
    response.headers["x-request-id"] = request_id
    return response


@app.api_route("/health", methods=["GET"], include_in_schema=False)
async def gateway_health():
    return {"status": "ok"}


@app.api_route("/ready", methods=["GET"], include_in_schema=False)
async def gateway_ready(request: Request):
    redis = getattr(request.app.state, "redis", None)
    if redis:
        try:
            await redis.ping()
        except Exception:
            return JSONResponse(status_code=503, content={"status": "redis_unavailable"})
    return {"status": "ready"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
async def gateway_proxy(request: Request, path: str):
    full_path = "/" + path if path else "/"
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    upstream_base, path_to_forward = get_upstream(full_path)
    query = str(request.url.query)

    need_jwt = _requires_jwt(full_path, request.method)
    user_id: int | None = None

    if need_jwt:
        auth = (request.headers.get("authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid authorization"})
        token = auth[7:].strip()
        payload = validate_jwt(token)
        if not payload:
            return JSONResponse(status_code=401, content={"detail": "Could not validate credentials"})
        sub = payload.get("sub")
        if sub is None:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})
        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})
        request.state.user_id = user_id

        redis = getattr(request.app.state, "redis", None)
        rl = await check_rate_limit(
            redis, f"user:{user_id}", GATEWAY_RATE_LIMIT_PER_USER
        )
        if not rl.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after_seconds": rl.retry_after_seconds,
                },
                headers={"Retry-After": str(rl.retry_after_seconds)},
            )
    else:
        redis = getattr(request.app.state, "redis", None)
        ip = _get_client_ip(request)
        rl = await check_rate_limit(redis, f"ip:{ip}", GATEWAY_RATE_LIMIT_PER_IP)
        if not rl.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after_seconds": rl.retry_after_seconds,
                },
                headers={"Retry-After": str(rl.retry_after_seconds)},
            )

    if request.method == "OPTIONS":
        return JSONResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Idempotency-Key, X-Request-ID, X-Webhook-Secret",
                "Access-Control-Max-Age": "86400",
            },
        )

    return await proxy_request(
        request,
        upstream_base,
        path_to_forward,
        query,
        user_id,
        request_id,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
