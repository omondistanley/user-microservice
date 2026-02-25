import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load .env from budget-microservice root before any app config is read (avoids 401 from missing SECRET_KEY)
_load_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_load_env)

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.routers import budgets
from app.core.config import get_cors_origins, SECRET_KEY

logger = logging.getLogger("budget_microservice")


def _log_request(request: Request, status_code: int = None, **extra):
    rid = getattr(request.state, "request_id", None)
    parts = [f"request_id={rid}"]
    if status_code is not None:
        parts.append(f"status_code={status_code}")
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    logger.info(" ".join(parts))


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
    request.state.request_id = str(uuid.uuid4())
    _log_request(request, method=request.method, path=request.url.path)
    response = await call_next(request)
    _log_request(request, status_code=response.status_code)
    return response


app = FastAPI(title="Budget Microservice")


@app.on_event("startup")
def _check_secret_key():
    if not (SECRET_KEY and SECRET_KEY.strip()):
        raise RuntimeError(
            "SECRET_KEY is empty. Copy .env from .env.example and set SECRET_KEY to match "
            "user-microservice, or budget API will return 401 Unauthorized."
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(structured_logging_middleware)
app.middleware("http")(cors_preflight_middleware)

app.include_router(budgets.router)


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "budget", "health": "/health"}


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3002)
