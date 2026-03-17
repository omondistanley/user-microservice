"""
Application configuration from environment variables.
Loads .env from project root (user-microservice/) so SECRET_KEY works locally.
Set SECRET_KEY (required for JWT). Optional: DB_* for data service context.
"""
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from user-microservice directory so it works regardless of cwd
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
ALGORITHM: str = os.environ.get("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
RESET_TOKEN_EXPIRE_HOURS: int = int(os.environ.get("RESET_TOKEN_EXPIRE_HOURS", "1"))

# Base URL for emails (reset link, verify link). e.g. http://localhost:8000
APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "http://localhost:8000")

# Email: "console" = log only, "smtp" = send via SMTP
EMAIL_MODE: str = os.environ.get("EMAIL_MODE", "console")
SMTP_HOST: Optional[str] = os.environ.get("SMTP_HOST")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.environ.get("SMTP_USER")
SMTP_PASSWORD: Optional[str] = os.environ.get("SMTP_PASSWORD")
SMTP_FROM: Optional[str] = os.environ.get("SMTP_FROM")

# Require email verification before login (set to false for local dev to allow unverified logins)
REQUIRE_EMAIL_VERIFICATION: bool = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "false").lower() in ("1", "true", "yes")

# Rate limiting (requests per minute per IP)
RATE_LIMIT_LOGIN_PER_MINUTE: int = int(os.environ.get("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
RATE_LIMIT_REGISTER_PER_MINUTE: int = int(os.environ.get("RATE_LIMIT_REGISTER_PER_MINUTE", "5"))
RATE_LIMIT_API_PER_MINUTE: int = int(os.environ.get("RATE_LIMIT_API_PER_MINUTE", "200"))
RATE_LIMIT_EXPENSIVE_PER_USER_PER_MINUTE: int = int(
    os.environ.get("RATE_LIMIT_EXPENSIVE_PER_USER_PER_MINUTE", "60")
)

# CORS: comma-separated origins, or * for allow all (dev). e.g. https://app.example.com
CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")
def get_cors_origins() -> list[str]:
    if not CORS_ORIGINS or CORS_ORIGINS.strip() == "*":
        return ["*"]
    return [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# Security headers
SECURITY_HEADERS_ENABLED: bool = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() in ("1", "true", "yes")
HSTS_MAX_AGE_SECONDS: int = int(os.environ.get("HSTS_MAX_AGE_SECONDS", "31536000"))
CSP_POLICY: str = os.environ.get(
    "CSP_POLICY",
    "default-src 'self' https: data: blob:; "
    "script-src 'self' 'nonce-{nonce}' https:; "
    "style-src 'self' 'unsafe-inline' https:; "
    "font-src 'self' https: data:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https:; "
    "frame-src 'self' https:; object-src 'none'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
)

# Proxy to expense, budget, and investments microservices (empty = disabled; defaults for local dev)
EXPENSE_SERVICE_URL: str = os.environ.get("EXPENSE_SERVICE_URL", "http://localhost:3001").rstrip("/")
BUDGET_SERVICE_URL: str = os.environ.get("BUDGET_SERVICE_URL", "http://localhost:3002").rstrip("/")
INVESTMENT_SERVICE_URL: str = os.environ.get("INVESTMENT_SERVICE_URL", "http://localhost:3003").rstrip("/")

# Frontend API base URLs (empty when proxy is used; e.g. http://localhost:3001 for non-proxy dev)
EXPENSE_API_BASE_FRONTEND: str = os.environ.get("EXPENSE_API_BASE_FRONTEND", "")
BUDGET_API_BASE_FRONTEND: str = os.environ.get("BUDGET_API_BASE_FRONTEND", "")

# When set (e.g. http://localhost:8080), frontend uses gateway for all API calls; proxy routes are disabled
GATEWAY_PUBLIC_URL: str = os.environ.get("GATEWAY_PUBLIC_URL", "").rstrip("/")

# JWT issuer/audience for downstream services
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "user-microservice")
JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "expense-tracker")

# OAuth: Google
GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# OAuth: Apple (Service ID, Team ID, Key ID, private key content or path to .p8 file)
APPLE_CLIENT_ID: str = os.environ.get("APPLE_CLIENT_ID", "")
APPLE_TEAM_ID: str = os.environ.get("APPLE_TEAM_ID", "")
APPLE_KEY_ID: str = os.environ.get("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY: str = os.environ.get("APPLE_PRIVATE_KEY", "")  # content or path
APPLE_REDIRECT_URI: str = os.environ.get("APPLE_REDIRECT_URI", "").rstrip("/")  # or derived from APP_BASE_URL

# Internal API key used by peer services (budget -> user notifications).
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")

# Rapid Email Validator (AbstractAPI or RapidAPI) - optional
RAPID_EMAIL_VALIDATOR_KEY: str = os.environ.get("RAPID_EMAIL_VALIDATOR_KEY", "")

# Optional DB context (fallback to hardcoded values in service_factory if unset)
DB_USER: Optional[str] = os.environ.get("DB_USER")
DB_PASSWORD: Optional[str] = os.environ.get("DB_PASSWORD")
DB_HOST: Optional[str] = os.environ.get("DB_HOST")
DB_PORT: Optional[str] = os.environ.get("DB_PORT")
DB_NAME: Optional[str] = os.environ.get("DB_NAME", "users_db")

# Internal service URLs used by background jobs.
EXPENSE_SERVICE_INTERNAL_URL: str = os.environ.get("EXPENSE_SERVICE_INTERNAL_URL", "http://localhost:3001").rstrip("/")
BUDGET_SERVICE_INTERNAL_URL: str = os.environ.get("BUDGET_SERVICE_INTERNAL_URL", "http://localhost:3002").rstrip("/")

# Webhook processing / validation config
WEBHOOK_MAX_ATTEMPTS: int = int(os.environ.get("WEBHOOK_MAX_ATTEMPTS", "5"))
WEBHOOK_BATCH_SIZE: int = int(os.environ.get("WEBHOOK_BATCH_SIZE", "25"))
WEBHOOK_RETRY_BASE_SECONDS: int = int(os.environ.get("WEBHOOK_RETRY_BASE_SECONDS", "30"))
WEBHOOK_SIGNATURE_TOLERANCE_SECONDS: int = int(os.environ.get("WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "300"))
WEBHOOK_SECRETS_JSON: str = os.environ.get("WEBHOOK_SECRETS_JSON", "{}")

# Calendar subscription token links.
CALENDAR_TOKEN_BASE_URL: str = os.environ.get("CALENDAR_TOKEN_BASE_URL", APP_BASE_URL.rstrip("/"))


def get_webhook_secrets() -> dict[str, str]:
    """Return provider->secret map from WEBHOOK_SECRETS_JSON, fail-closed to empty map."""
    try:
        data = json.loads(WEBHOOK_SECRETS_JSON or "{}")
        if isinstance(data, dict):
            out: dict[str, str] = {}
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                    out[k.strip().lower()] = v.strip()
            return out
    except Exception:
        pass
    return {}
