"""
Gateway configuration from environment.
SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE must match user-microservice.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
ALGORITHM: str = os.environ.get("ALGORITHM", "HS256")
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "user-microservice")
JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "expense-tracker")

# Empty when unset so gateway runs without Redis (e.g. Fly single-app); set for shared rate limiting.
REDIS_URL: str = (os.environ.get("REDIS_URL") or "").strip()

USER_SERVICE_URL: str = os.environ.get("USER_SERVICE_URL", "http://user:8000").rstrip("/")
EXPENSE_SERVICE_URL: str = os.environ.get("EXPENSE_SERVICE_URL", "http://expense:3001").rstrip("/")
BUDGET_SERVICE_URL: str = os.environ.get("BUDGET_SERVICE_URL", "http://budget:3002").rstrip("/")
INVESTMENT_SERVICE_URL: str = os.environ.get("INVESTMENT_SERVICE_URL", "http://investment:3003").rstrip("/")

GATEWAY_RATE_LIMIT_PER_USER: int = int(os.environ.get("GATEWAY_RATE_LIMIT_PER_USER", "200"))
GATEWAY_RATE_LIMIT_PER_IP: int = int(os.environ.get("GATEWAY_RATE_LIMIT_PER_IP", "300"))
PROXY_TIMEOUT_SECONDS: float = float(os.environ.get("PROXY_TIMEOUT_SECONDS", "60"))

CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")


def get_cors_origins() -> list[str]:
    if not CORS_ORIGINS or CORS_ORIGINS.strip() == "*":
        return ["*"]
    return [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
