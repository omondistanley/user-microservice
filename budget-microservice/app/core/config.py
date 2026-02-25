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

# CORS: comma-separated origins, or * for allow all
CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")


def get_cors_origins() -> list[str]:
    if not CORS_ORIGINS or CORS_ORIGINS.strip() == "*":
        return ["*"]
    return [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
