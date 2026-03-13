"""
Application configuration from environment variables.
SECRET_KEY must match user-microservice for JWT validation.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
ALGORITHM: str = os.environ.get("ALGORITHM", "HS256")
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "user-microservice")
JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "expense-tracker")

DB_USER: Optional[str] = os.environ.get("DB_USER")
DB_PASSWORD: Optional[str] = os.environ.get("DB_PASSWORD")
DB_HOST: Optional[str] = os.environ.get("DB_HOST")
DB_PORT: Optional[str] = os.environ.get("DB_PORT")
DB_NAME: Optional[str] = os.environ.get("DB_NAME", os.environ.get("INVESTMENTS_DB_NAME", "investments_db"))

INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")
CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

# Market data providers (both can be enabled; adapter decides routing/fallback)
ALPACA_API_KEY: str = os.environ.get("ALPACA_API_KEY", "")
ALPACA_API_SECRET: str = os.environ.get("ALPACA_API_SECRET", "")
ALPACA_DATA_BASE_URL: str = os.environ.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets").rstrip("/")

FREE_MARKET_API_KEY: str = os.environ.get("FREE_MARKET_API_KEY", "")
FREE_MARKET_BASE_URL: str = os.environ.get("FREE_MARKET_BASE_URL", "https://finnhub.io/api/v1").rstrip("/")

# Portfolio analytics / recommendation tunables
RISK_FREE_RATE_ANNUAL: float = float(os.environ.get("RISK_FREE_RATE_ANNUAL", "0.02"))
MARKET_DATA_PROVIDER_ORDER: str = os.environ.get("MARKET_DATA_PROVIDER_ORDER", "alpaca,free")


def get_cors_origins() -> list:
    if not CORS_ORIGINS or CORS_ORIGINS.strip() == "*":
        return ["*"]
    return [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

SECURITY_HEADERS_ENABLED: bool = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() in ("1", "true", "yes")
HSTS_MAX_AGE_SECONDS: int = int(os.environ.get("HSTS_MAX_AGE_SECONDS", "31536000"))
API_CSP_POLICY: str = os.environ.get(
    "API_CSP_POLICY",
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
)
