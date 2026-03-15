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

# Additional free market data providers (Finnhub, TwelveData, Alpha Vantage)
FINNHUB_API_KEY: str = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE_URL: str = os.environ.get("FINNHUB_BASE_URL", "https://finnhub.io/api/v1").rstrip("/")
TWELVEDATA_API_KEY: str = os.environ.get("TWELVEDATA_API_KEY", "")
TWELVEDATA_BASE_URL: str = os.environ.get("TWELVEDATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")
ALPHAVANTAGE_API_KEY: str = os.environ.get("ALPHAVANTAGE_API_KEY", "")
ALPHAVANTAGE_BASE_URL: str = os.environ.get("ALPHAVANTAGE_BASE_URL", "https://www.alphavantage.co").rstrip("/")

# Portfolio analytics / recommendation tunables
RISK_FREE_RATE_ANNUAL: float = float(os.environ.get("RISK_FREE_RATE_ANNUAL", "0.02"))
MARKET_DATA_PROVIDER_ORDER: str = os.environ.get(
    "MARKET_DATA_PROVIDER_ORDER", "alpaca,finnhub,twelvedata,alphavantage"
)
# Quote cache: skip provider call if we have a quote younger than this (seconds)
QUOTE_CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("QUOTE_CACHE_MAX_AGE_SECONDS", "60"))
# If new quote deviates from last known price by more than this fraction (e.g. 0.05 = 5%), log and set data_quality
MARKET_QUOTE_DEVIATION_PCT: float = float(os.environ.get("MARKET_QUOTE_DEVIATION_PCT", "0.05"))
# Provider status cache TTL (seconds) to avoid hammering status() endpoints
MARKET_PROVIDER_STATUS_CACHE_SECONDS: int = int(
    os.environ.get("MARKET_PROVIDER_STATUS_CACHE_SECONDS", "60")
)

# Optional AI explainer for recommendation narratives (tri-provider: generic, Groq, Brave)
AI_EXPLAINER_API_BASE: str = os.environ.get("AI_EXPLAINER_API_BASE", "").rstrip("/")
AI_EXPLAINER_API_KEY: str = os.environ.get("AI_EXPLAINER_API_KEY", "")
AI_EXPLAINER_MODEL: str = os.environ.get("AI_EXPLAINER_MODEL", "")
AI_EXPLAINER_PROVIDER_ORDER: str = os.environ.get("AI_EXPLAINER_PROVIDER_ORDER", "groq,brave,generic")
# Groq (OpenAI-compatible; free tier rate limits apply)
GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT_SECONDS: int = int(os.environ.get("GROQ_TIMEOUT_SECONDS", "6"))
GROQ_MAX_TOKENS: int = int(os.environ.get("GROQ_MAX_TOKENS", "150"))
# Brave (chat completions; free credits monthly)
BRAVE_API_BASE: str = os.environ.get("BRAVE_API_BASE", "https://api.search.brave.com/res/v1").rstrip("/")
BRAVE_API_KEY: str = os.environ.get("BRAVE_API_KEY", "")
BRAVE_MODEL: str = os.environ.get("BRAVE_MODEL", "brave")
BRAVE_TIMEOUT_SECONDS: int = int(os.environ.get("BRAVE_TIMEOUT_SECONDS", "8"))
# Generic explainer timeout; narrative max length (chars) for truncation/post-process
AI_EXPLAINER_TIMEOUT_SECONDS: int = int(os.environ.get("AI_EXPLAINER_TIMEOUT_SECONDS", "10"))
AI_EXPLAINER_MAX_NARRATIVE_CHARS: int = int(os.environ.get("AI_EXPLAINER_MAX_NARRATIVE_CHARS", "500"))


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
