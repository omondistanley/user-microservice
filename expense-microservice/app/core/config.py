"""
Application configuration from environment variables.
Loads .env from project root (expense-microservice/) so SECRET_KEY works locally.
Set SECRET_KEY (must match user-microservice for JWT). Optional: DB_* for data service context.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from expense-microservice directory so it works regardless of cwd
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
ALGORITHM: str = os.environ.get("ALGORITHM", "HS256")
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "user-microservice")
JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "expense-tracker")

# DB context for expense service (schema expenses_db)
DB_USER: Optional[str] = os.environ.get("DB_USER")
DB_PASSWORD: Optional[str] = os.environ.get("DB_PASSWORD")
DB_HOST: Optional[str] = os.environ.get("DB_HOST")
DB_PORT: Optional[str] = os.environ.get("DB_PORT")
DB_NAME: Optional[str] = os.environ.get("DB_NAME", os.environ.get("EXPENSE_DB_NAME", "expenses_db"))

# Receipt file storage: "local" (filesystem) or "db" (BLOB in receipt row)
RECEIPT_STORAGE_BACKEND: str = os.environ.get("RECEIPT_STORAGE_BACKEND", "local")
# For local backend: directory path (relative to app root or absolute)
RECEIPT_STORAGE_PATH: str = os.environ.get("RECEIPT_STORAGE_PATH", "receipts")

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

# Rate limiting (requests per minute per IP for POST /api/v1/expenses)
RATE_LIMIT_EXPENSES_PER_MINUTE: int = int(os.environ.get("RATE_LIMIT_EXPENSES_PER_MINUTE", "60"))

# Plaid (empty = Plaid routes disabled or return 503)
PLAID_CLIENT_ID: str = os.environ.get("PLAID_CLIENT_ID", "")
PLAID_SECRET: str = os.environ.get("PLAID_SECRET", "")
PLAID_ENV: str = os.environ.get("PLAID_ENV", "sandbox")  # sandbox, development, production
# Fernet key for encrypting access_token (32 bytes base64). Generate: from cryptography.fernet import Fernet; Fernet.generate_key()
ENCRYPTION_KEY: Optional[str] = os.environ.get("ENCRYPTION_KEY", "")

# Internal API key used by trusted peer services (e.g. user-microservice purge orchestration).
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")
