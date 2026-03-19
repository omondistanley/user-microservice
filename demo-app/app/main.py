"""pocketii demo: Watch + Interactive. Render-ready."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from datetime import datetime, timezone

from app.config import DEMO_IDLE_RESET_SECONDS, DEMO_RESET_INTERVAL_SECONDS
from app.db import (
    ensure_watch_seed,
    init_db,
    last_activity_iso,
    last_reset_iso,
    reset_demo_data,
)
from app.limiter_util import limiter
from app.routers import api_demo, narrate, pages, session

_static = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_watch_seed()
    sched = AsyncIOScheduler()

    def job():
        now = datetime.now(timezone.utc)

        def _parse(value: str) -> Optional[datetime]:
            if not value:
                return None
            try:
                dt = datetime.fromisoformat(value)
            except Exception:
                # sqlite datetime('now') default format: "YYYY-MM-DD HH:MM:SS"
                try:
                    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        last_act = _parse(last_activity_iso() or "")
        last_reset = _parse(last_reset_iso() or "")

        idle_age = (now - last_act).total_seconds() if last_act else None
        interval_age = (now - last_reset).total_seconds() if last_reset else None

        idle_due = (idle_age is None) or (idle_age >= DEMO_IDLE_RESET_SECONDS)
        interval_due = (interval_age is None) or (interval_age >= DEMO_RESET_INTERVAL_SECONDS)

        # Reset either when idle or when the periodic safety interval elapses.
        if idle_due or interval_due:
            reset_demo_data()
            ensure_watch_seed()

    # Check frequently enough to satisfy "idle reset" requirements.
    check_seconds = max(10, min(60, DEMO_IDLE_RESET_SECONDS))
    sched.add_job(job, "interval", seconds=check_seconds, id="demo_reset")
    sched.start()
    yield
    sched.shutdown()


app = FastAPI(title="pocketii demo", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory=str(_static)), name="static")

app.include_router(pages.router)
app.include_router(session.router)
app.include_router(api_demo.router)
app.include_router(narrate.router)

# Ensure tables exist before first request (TestClient may not run lifespan the same as prod)
init_db()
