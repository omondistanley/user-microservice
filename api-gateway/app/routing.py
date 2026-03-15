"""
Path prefix to upstream base URL. Longest prefix wins; order matters.
"""
from app.config import (
    BUDGET_SERVICE_URL,
    EXPENSE_SERVICE_URL,
    INVESTMENT_SERVICE_URL,
    USER_SERVICE_URL,
)

# List of (path_prefix, upstream_base). First match wins; list more specific first.
ROUTES: list[tuple[str, str]] = [
    # Expense
    ("/api/v1/expenses", EXPENSE_SERVICE_URL),
    ("/api/v1/income", EXPENSE_SERVICE_URL),
    ("/api/v1/cashflow", EXPENSE_SERVICE_URL),
    ("/api/v1/recurring-expenses", EXPENSE_SERVICE_URL),
    ("/api/v1/categories", EXPENSE_SERVICE_URL),
    ("/api/v1/tags", EXPENSE_SERVICE_URL),
    ("/api/v1/receipts", EXPENSE_SERVICE_URL),
    ("/api/v1/plaid", EXPENSE_SERVICE_URL),
    ("/api/v1/teller", EXPENSE_SERVICE_URL),
    ("/api/v1/truelayer", EXPENSE_SERVICE_URL),
    ("/api/v1/bank", EXPENSE_SERVICE_URL),
    ("/api/v1/goals", EXPENSE_SERVICE_URL),
    ("/api/v1/insights", EXPENSE_SERVICE_URL),
    ("/api/v1/reminders", EXPENSE_SERVICE_URL),
    ("/api/v1/export", EXPENSE_SERVICE_URL),
    # Budget
    ("/api/v1/budgets", BUDGET_SERVICE_URL),
    # Investment
    ("/api/v1/holdings", INVESTMENT_SERVICE_URL),
    ("/api/v1/recommendations", INVESTMENT_SERVICE_URL),
    ("/api/v1/portfolio", INVESTMENT_SERVICE_URL),
    ("/api/v1/market", INVESTMENT_SERVICE_URL),
    ("/api/v1/risk-profile", INVESTMENT_SERVICE_URL),
]

DEFAULT_UPSTREAM = USER_SERVICE_URL


def get_upstream(path: str) -> tuple[str, str]:
    """
    Return (upstream_base_url, path_to_forward).
    path_to_forward is the full path (e.g. /api/v1/expenses/123) for the upstream.
    """
    path = path or "/"
    if not path.startswith("/"):
        path = "/" + path
    for prefix, base in ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            return (base, path)
    return (DEFAULT_UPSTREAM, path)
