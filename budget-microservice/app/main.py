import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from budget-microservice root before any app config is read (avoids 401 from missing SECRET_KEY)
_load_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_load_env)

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.routers import budgets, internal, recurring_budgets
from app.core.config import (
    REDIS_URL,
    get_cors_origins,
    SECRET_KEY,
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    SECURITY_HEADERS_ENABLED,
    HSTS_MAX_AGE_SECONDS,
    API_CSP_POLICY,
)
from app.core.security import decode_token
from app.events.subscriber import run_subscriber

logger = logging.getLogger("budget_microservice")


def _log_json(level: str, **fields):
    line = json.dumps(fields, default=str, separators=(",", ":"))
    if level == "error":
        logger.error(line)
    else:
        logger.info(line)


def _extract_user_id(request: Request) -> int | None:
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except Exception:
        return None


def _db_readiness_check() -> tuple[bool, str | None]:
    try:
        conn = psycopg2.connect(
            host=DB_HOST or "localhost",
            port=int(DB_PORT) if DB_PORT else 5432,
            user=DB_USER or "postgres",
            password=DB_PASSWORD or "postgres",
            dbname=DB_NAME or "budgets_db",
            connect_timeout=3,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


async def cors_preflight_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        origin = request.headers.get("origin", "*")
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin if origin else "*",
                "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "86400",
            },
        )
    return await call_next(request)


async def structured_logging_middleware(request: Request, call_next):
    incoming = (request.headers.get("x-request-id") or "").strip()
    request_id = incoming if incoming else str(uuid.uuid4())
    request.state.request_id = request_id
    user_id = _extract_user_id(request)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        payload = {
            "service": "budget",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "duration_ms": duration_ms,
        }
        if user_id is not None:
            payload["user_id"] = user_id
        _log_json("error", **payload)
        raise
    response.headers["X-Request-ID"] = request_id
    duration_ms = round((time.perf_counter() - start) * 1000, 3)
    payload = {
        "service": "budget",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }
    if user_id is not None:
        payload["user_id"] = user_id
    _log_json("info", **payload)
    return response


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if not SECURITY_HEADERS_ENABLED:
        return response
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", API_CSP_POLICY)
    if HSTS_MAX_AGE_SECONDS > 0:
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains",
        )
    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not (SECRET_KEY and SECRET_KEY.strip()):
        raise RuntimeError(
            "SECRET_KEY is empty. Copy .env from .env.example and set SECRET_KEY to match "
            "user-microservice, or budget API will return 401 Unauthorized."
        )
    subscriber_task = None
    if REDIS_URL and REDIS_URL.strip():
        subscriber_task = asyncio.create_task(run_subscriber())
    yield
    if subscriber_task is not None:
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Budget Microservice", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(structured_logging_middleware)
app.middleware("http")(cors_preflight_middleware)
app.middleware("http")(security_headers_middleware)

app.include_router(budgets.router)
app.include_router(recurring_budgets.router)
app.include_router(internal.router)


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "budget", "health": "/health"}


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def ready():
    ok, _ = _db_readiness_check()
    if ok:
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "not_ready"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3002)
