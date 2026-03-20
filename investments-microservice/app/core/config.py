"""
Application configuration from environment variables.
SECRET_KEY must match user-microservice for JWT validation.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_service_root = Path(__file__).resolve().parent.parent.parent
_repo_root = _service_root.parent
# Service-local .env first; repo root .env fills missing keys (Docker often injects env, local dev may only use root .env).
load_dotenv(_service_root / ".env")
load_dotenv(_repo_root / ".env", override=False)

SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
ALGORITHM: str = os.environ.get("ALGORITHM", "HS256")
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "user-microservice")
JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "expense-tracker")

DB_USER: Optional[str] = os.environ.get("DB_USER")
DB_PASSWORD: Optional[str] = os.environ.get("DB_PASSWORD")
DB_HOST: Optional[str] = os.environ.get("DB_HOST")
DB_PORT: Optional[str] = os.environ.get("DB_PORT")
DB_NAME: Optional[str] = os.environ.get("DB_NAME", os.environ.get("INVESTMENTS_DB_NAME", "investments_db"))

# Optional symmetric key for encrypting third-party credentials (e.g. Alpaca API keys),
# shared pattern with expense-microservice ENCRYPTION_KEY.
ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY", "")

INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")
USER_SERVICE_INTERNAL_URL: str = os.environ.get("USER_SERVICE_INTERNAL_URL", "http://localhost:8000").rstrip("/")
LIVE_TRADING_ENABLED: bool = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in ("1", "true", "yes", "y", "on")
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
# Max recommendations per run (holdings + universe suggestions); page size for list API
MAX_RECOMMENDATIONS: int = int(os.environ.get("MAX_RECOMMENDATIONS", "100"))
RECOMMENDATIONS_PAGE_SIZE: int = int(os.environ.get("RECOMMENDATIONS_PAGE_SIZE", "20"))
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

# Sector exposure (6.1): cache TTL and concentration warning threshold
SECTOR_CACHE_TTL_HOURS: int = int(os.environ.get("SECTOR_CACHE_TTL_HOURS", "24"))
SECTOR_CONCENTRATION_THRESHOLD_PCT: float = float(
    os.environ.get("SECTOR_CONCENTRATION_THRESHOLD_PCT", "35")
)

# Tax-loss harvesting (6.4): minimum $ loss to suggest harvesting; Redis for events
TAX_LOSS_THRESHOLD_DOLLARS: float = float(os.environ.get("TAX_LOSS_THRESHOLD_DOLLARS", "200"))
REDIS_URL: Optional[str] = os.environ.get("REDIS_URL")

# ETF look-through (6.2): composition file URLs per symbol (JSON: {"SPY":"https://...", "IVV":"https://..."})
ETF_COMPOSITION_URLS: str = os.environ.get("ETF_COMPOSITION_URLS", "{}")
# Comma-separated ETF symbols to sync when no URL map; job also syncs symbols from user holdings
ETF_SYMBOLS_TO_SYNC: str = os.environ.get("ETF_SYMBOLS_TO_SYNC", "SPY,IVV,VOO,QQQ")

# News pipeline (Benzinga primary, Finnhub/Alpha Vantage supplement)
BENZINGA_API_KEY: str = os.environ.get("BENZINGA_API_KEY", "")
BENZINGA_BASE_URL: str = os.environ.get("BENZINGA_BASE_URL", "https://api.benzinga.com").rstrip("/")
NEWS_PROVIDER_ORDER: str = os.environ.get("NEWS_PROVIDER_ORDER", "benzinga,finnhub,alphavantage")
NEWS_TIMEOUT_SECONDS: int = int(os.environ.get("NEWS_TIMEOUT_SECONDS", "8"))
NEWS_PAGE_SIZE: int = int(os.environ.get("NEWS_PAGE_SIZE", "20"))

# FinBERT sentiment (6.7): alert when 7d rolling avg below threshold for 2 consecutive days
SENTIMENT_THRESHOLD: float = float(os.environ.get("SENTIMENT_THRESHOLD", "-0.3"))
SENTIMENT_LOOKBACK_DAYS: int = int(os.environ.get("SENTIMENT_LOOKBACK_DAYS", "7"))

# Finance context for personalization: gateway or expense service URL (used with user JWT from request)
GATEWAY_PUBLIC_URL: str = os.environ.get("GATEWAY_PUBLIC_URL", "").rstrip("/")
EXPENSE_SERVICE_URL: str = os.environ.get("EXPENSE_SERVICE_URL", "").rstrip("/")
FINANCE_CONTEXT_TIMEOUT_SECONDS: float = float(os.environ.get("FINANCE_CONTEXT_TIMEOUT_SECONDS", "8"))


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
