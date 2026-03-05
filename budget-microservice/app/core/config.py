"""
Application configuration from environment variables.
Loads .env from project root (budget-microservice/) so SECRET_KEY works locally.
Set SECRET_KEY (must match user-microservice for JWT). Optional: DB_* for data service context.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from budget-microservice directory so it works regardless of cwd
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
ALGORITHM: str = os.environ.get("ALGORITHM", "HS256")
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "user-microservice")
JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "expense-tracker")

# DB context for budget service (schema budgets_db)
DB_USER: Optional[str] = os.environ.get("DB_USER")
DB_PASSWORD: Optional[str] = os.environ.get("DB_PASSWORD")
DB_HOST: Optional[str] = os.environ.get("DB_HOST")
DB_PORT: Optional[str] = os.environ.get("DB_PORT")
DB_NAME: Optional[str] = os.environ.get("DB_NAME", os.environ.get("BUDGET_DB_NAME", "budgets_db"))

# Optional expense DB context used for alert evaluation spend totals.
EXPENSE_DB_USER: Optional[str] = os.environ.get("EXPENSE_DB_USER", DB_USER)
EXPENSE_DB_PASSWORD: Optional[str] = os.environ.get("EXPENSE_DB_PASSWORD", DB_PASSWORD)
EXPENSE_DB_HOST: Optional[str] = os.environ.get("EXPENSE_DB_HOST", DB_HOST)
EXPENSE_DB_PORT: Optional[str] = os.environ.get("EXPENSE_DB_PORT", DB_PORT)
EXPENSE_DB_NAME: Optional[str] = os.environ.get("EXPENSE_DB_NAME", "expenses_db")

# Internal notification target (user service) for in-app alert fanout.
USER_SERVICE_INTERNAL_URL: str = os.environ.get("USER_SERVICE_INTERNAL_URL", "http://localhost:8000").rstrip("/")
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")

# CORS: comma-separated origins, or * for allow all
CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")


def get_cors_origins() -> list[str]:
    if not CORS_ORIGINS or CORS_ORIGINS.strip() == "*":
        return ["*"]
    return [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# Security headers
SECURITY_HEADERS_ENABLED: bool = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() in ("1", "true", "yes")
HSTS_MAX_AGE_SECONDS: int = int(os.environ.get("HSTS_MAX_AGE_SECONDS", "31536000"))
API_CSP_POLICY: str = os.environ.get(
    "API_CSP_POLICY",
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
)
