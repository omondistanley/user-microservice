"""
IRA-specific informational features.
All output is informational only — not financial advice.
"""
from datetime import date
from typing import Optional

DISCLAIMER = "Not financial advice. For informational purposes only."

IRA_CONTRIBUTION_LIMITS = {
    "traditional_ira": {"under_50": 7000, "over_50": 8000},
    "roth_ira": {"under_50": 7000, "over_50": 8000},
    "hsa": {"self_only": 4150, "family": 8300},
}

# IRS RMD life expectancy table (Uniform Lifetime, age → divisor)
_RMD_DIVISORS = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9,
    78: 22.0, 79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7,
    84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9,
    90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9,
    96: 8.4, 97: 7.8, 98: 7.3, 99: 6.8, 100: 6.4,
}


def get_rmd_banner(dob: date, ira_balance: float) -> Optional[dict]:
    """
    Returns RMD informational banner if user is 72+.
    Returns None if under 72 or balance is 0.
    """
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 72 or ira_balance <= 0:
        return None
    divisor = _RMD_DIVISORS.get(min(age, 100), 6.4)
    estimated_rmd = round(ira_balance / divisor, 2)
    return {
        "type": "rmd_banner",
        "age": age,
        "estimated_rmd": estimated_rmd,
        "message": (
            f"Based on your age ({age}) and IRA balance, your estimated annual RMD is "
            f"${estimated_rmd:,.2f}. This is informational only — consult a tax adviser."
        ),
        "disclaimer": DISCLAIMER,
    }


def get_contribution_headroom(account_type: str, ytd_contributions: float, age: int) -> dict:
    """
    Returns remaining contribution room for IRA/HSA accounts.
    account_type: 'traditional_ira' | 'roth_ira' | 'hsa'
    """
    account_type = account_type.lower().replace(" ", "_")
    limits = IRA_CONTRIBUTION_LIMITS.get(account_type)
    if not limits:
        return {"headroom": None, "disclaimer": DISCLAIMER}

    if account_type == "hsa":
        limit = limits["self_only"]
    else:
        limit = limits["over_50"] if age >= 50 else limits["under_50"]

    headroom = max(0.0, limit - ytd_contributions)
    return {
        "account_type": account_type,
        "annual_limit": limit,
        "ytd_contributions": ytd_contributions,
        "headroom": headroom,
        "headroom_monthly": round(headroom / max(1, 12 - date.today().month + 1), 2),
        "disclaimer": DISCLAIMER,
    }


def suggest_asset_location(positions: list) -> list:
    """
    Returns asset location suggestions based on account type and asset class.
    Informational guidance only — no buy/sell language.
    positions: list of dicts with keys: symbol, account_type, asset_class (optional)
    """
    suggestions = []
    BOND_KEYWORDS = {"bond", "fixed", "treasury", "govt", "muni", "tip", "bnd", "agg", "shy", "ief", "tlt"}
    REIT_KEYWORDS = {"reit", "real estate", "vnq", "schh", "xlre"}
    GROWTH_KEYWORDS = {"growth", "tech", "qqq", "vgt", "arkk"}

    for pos in positions:
        symbol_lower = pos.get("symbol", "").lower()
        account_type = (pos.get("account_type") or "taxable").lower()
        asset_class = (pos.get("asset_class") or "").lower()

        is_bond = any(k in symbol_lower or k in asset_class for k in BOND_KEYWORDS)
        is_reit = any(k in symbol_lower or k in asset_class for k in REIT_KEYWORDS)
        is_growth = any(k in symbol_lower or k in asset_class for k in GROWTH_KEYWORDS)

        if is_bond and account_type == "taxable":
            suggestions.append({
                "symbol": pos["symbol"],
                "current_account": account_type,
                "observation": "Bond/fixed income holdings in taxable accounts may generate taxable interest. "
                               "Tax-advantaged accounts (Traditional IRA, 401k) are one approach for income-generating assets.",
                "severity": "info",
            })
        elif is_reit and account_type == "taxable":
            suggestions.append({
                "symbol": pos["symbol"],
                "current_account": account_type,
                "observation": "REITs distribute most income as ordinary dividends. "
                               "Holding in a tax-advantaged account is one approach to consider.",
                "severity": "info",
            })
        elif is_growth and account_type in ("traditional_ira", "401k"):
            suggestions.append({
                "symbol": pos["symbol"],
                "current_account": account_type,
                "observation": "Growth assets in Traditional IRA/401k will be taxed as ordinary income on withdrawal. "
                               "Roth accounts are one approach for long-horizon growth assets.",
                "severity": "info",
            })

    return suggestions


def get_roth_conversion_nudge(
    trad_ira_balance: float,
    estimated_income: float,
    age: int,
    tax_bracket: Optional[str] = None,
) -> Optional[dict]:
    """
    Returns Roth conversion informational nudge when conditions suggest it may be worth reviewing.
    Returns None if no relevant conditions met.
    """
    if trad_ira_balance <= 0 or age >= 73:
        return None
    # Low income year or pre-RMD window
    low_income = estimated_income < 50000
    pre_rmd = 60 <= age < 72
    if not (low_income or pre_rmd):
        return None

    reason = []
    if low_income:
        reason.append("estimated income suggests a lower tax bracket this year")
    if pre_rmd:
        reason.append("you are in the pre-RMD window (ages 60–72)")

    return {
        "type": "roth_conversion_nudge",
        "message": (
            f"Roth conversion is one approach some people consider when {' and '.join(reason)}. "
            "Converting moves money from Traditional IRA to Roth IRA, creating a taxable event now "
            "in exchange for tax-free growth later. Consult a tax adviser to evaluate your situation."
        ),
        "trad_ira_balance": trad_ira_balance,
        "disclaimer": DISCLAIMER,
    }
