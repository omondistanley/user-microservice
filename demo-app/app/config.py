"""Demo app config — no Plaid/Alpaca/etc. Only demo JWT and optional AI."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEMO_JWT_SECRET: str = os.environ.get("DEMO_JWT_SECRET", "change-me-in-production-demo-only")
DEMO_JWT_EXPIRE_MINUTES: int = int(os.environ.get("DEMO_JWT_EXPIRE_MINUTES", "120"))
DEMO_DB_PATH: str = os.environ.get("DEMO_DB_PATH", str(ROOT / "data" / "demo.db"))

# Reset interactive data every N seconds (APScheduler)
DEMO_RESET_INTERVAL_SECONDS: int = int(os.environ.get("DEMO_RESET_INTERVAL_SECONDS", "900"))
# Also reset if no activity for M seconds (checked on each request + on schedule)
DEMO_IDLE_RESET_SECONDS: int = int(os.environ.get("DEMO_IDLE_RESET_SECONDS", "1800"))

# Rate limits
DEMO_SESSION_CREATE_PER_HOUR: int = int(os.environ.get("DEMO_SESSION_CREATE_PER_HOUR", "30"))
DEMO_API_PER_MINUTE: int = int(os.environ.get("DEMO_API_PER_MINUTE", "120"))

# Hard caps to limit sandbox growth / corruption.
DEMO_MAX_EXPENSES_PER_SESSION: int = int(os.environ.get("DEMO_MAX_EXPENSES_PER_SESSION", "200"))
DEMO_MAX_BUDGETS_PER_SESSION: int = int(os.environ.get("DEMO_MAX_BUDGETS_PER_SESSION", "100"))
DEMO_MAX_INCOME_PER_SESSION: int = int(os.environ.get("DEMO_MAX_INCOME_PER_SESSION", "100"))
DEMO_MAX_GOALS_PER_SESSION: int = int(os.environ.get("DEMO_MAX_GOALS_PER_SESSION", "50"))

# Optional AI narrative (default off)
DEMO_AI_ENABLED: bool = os.environ.get("DEMO_AI_ENABLED", "").lower() in ("1", "true", "yes")
DEMO_AI_API_URL: str = os.environ.get("DEMO_AI_API_URL", "").strip()
DEMO_AI_API_KEY: str = os.environ.get("DEMO_AI_API_KEY", "").strip()
DEMO_AI_MODEL: str = os.environ.get("DEMO_AI_MODEL", "gpt-4o-mini")
DEMO_AI_DAILY_CAP: int = int(os.environ.get("DEMO_AI_DAILY_CAP", "200"))

PUBLIC_BASE_URL: str = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
