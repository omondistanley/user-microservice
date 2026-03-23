"""
Sprint 3: EDGAR Form 4 insider transaction data fetcher.

SEC EDGAR provides Form 4 filings (insider buy/sell) for free via its public
REST API — no API key required.  This is one of the highest-signal free data
sources for equity analysis: clusters of insider purchases have historically
preceded positive price moves; large insider sales are a caution signal.

API used:
  https://data.sec.gov/submissions/{cik}.json
  https://data.sec.gov/api/xbrl/companyfacts/{cik}.json  (not used here)
  https://efts.sec.gov/LATEST/search-index?q=%22{symbol}%22&dateRange=custom&...

We use the submissions endpoint because:
  - It provides structured recent filings per CIK (Central Index Key).
  - Form 4 (insider ownership changes) and Form 4/A (amendments) are filterable.
  - Rate limit: SEC asks for <= 10 requests/second; we stay well below with caching.

Data flow:
  1. symbol → CIK  via SEC ticker map (https://www.sec.gov/files/company_tickers.json)
  2. CIK     → recent Form 4 filings  (submissions endpoint)
  3. Parse transaction type (P=purchase, S=sale) + value + date
  4. Compute a net insider sentiment score in [-1, 1]:
       +1 = all insiders buying, -1 = all insiders selling
       score = (purchase_value - sale_value) / (purchase_value + sale_value + ε)
  5. Return structured dict consumed by sentiment_service.py fusion layer.

Caching:
  - CIK map is module-level; fetched once per process, never expires (stable).
  - Submission data is cached per CIK with a TTL of 24 h to respect SEC rate limits.
  - All HTTP failures are swallowed and return a neutral score (0.0) so the
    recommendation engine always succeeds regardless of EDGAR availability.
"""
import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_SEC_HEADERS = {
    # SEC requires a descriptive User-Agent identifying the application and contact.
    "User-Agent": "pocketii-personal-finance dev@pocketii.app",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}
_SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_REQUEST_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# Module-level CIK map cache  (symbol → zero-padded 10-digit CIK string)
# Populated lazily on first call; stable across process lifetime.
# ---------------------------------------------------------------------------
_cik_map_lock = threading.Lock()
_cik_map: Optional[Dict[str, str]] = None   # {"AAPL": "0000320193", ...}
_cik_map_fetched_at: float = 0.0

# Per-CIK submission cache  { cik: (timestamp, data_dict) }
_submission_cache: Dict[str, Tuple[float, Dict]] = {}
_submission_cache_lock = threading.Lock()
_SUBMISSION_TTL_SECONDS = 86_400  # 24 hours


def _fetch_cik_map() -> Dict[str, str]:
    """
    Fetch the SEC full-company ticker JSON and build symbol→CIK lookup.
    Returns empty dict on failure.
    """
    try:
        resp = requests.get(
            _SEC_TICKER_URL,
            headers={"User-Agent": "pocketii-personal-finance dev@pocketii.app"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()
        # Format: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ... }
        result: Dict[str, str] = {}
        for entry in raw.values():
            ticker = (entry.get("ticker") or "").strip().upper()
            cik_raw = entry.get("cik_str")
            if ticker and cik_raw:
                result[ticker] = str(cik_raw).zfill(10)
        logger.info("edgar_cik_map_loaded: %d symbols", len(result))
        return result
    except Exception as exc:
        logger.warning("edgar_cik_map_fetch_failed: %s", exc)
        return {}


def _get_cik_map() -> Dict[str, str]:
    """Return module-level CIK map, fetching once on first call."""
    global _cik_map, _cik_map_fetched_at
    if _cik_map is None:
        with _cik_map_lock:
            if _cik_map is None:
                _cik_map = _fetch_cik_map()
                _cik_map_fetched_at = time.monotonic()
    return _cik_map or {}


def symbol_to_cik(symbol: str) -> Optional[str]:
    """Return zero-padded 10-digit CIK for a ticker symbol, or None."""
    return _get_cik_map().get(symbol.strip().upper())


def _fetch_submissions(cik: str) -> Dict[str, Any]:
    """
    Fetch the SEC submissions JSON for a CIK.  Results are cached for 24 h.
    Returns empty dict on failure.
    """
    now = time.monotonic()
    with _submission_cache_lock:
        cached = _submission_cache.get(cik)
        if cached and (now - cached[0]) < _SUBMISSION_TTL_SECONDS:
            return cached[1]

    url = _SEC_SUBMISSIONS_URL.format(cik=cik)
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        with _submission_cache_lock:
            _submission_cache[cik] = (now, data)
        return data
    except Exception as exc:
        logger.warning("edgar_submissions_fetch_failed cik=%s: %s", cik, exc)
        return {}


def get_recent_form4_transactions(
    symbol: str,
    lookback_days: int = 90,
) -> List[Dict[str, Any]]:
    """
    Return recent Form 4 insider transactions for `symbol` within `lookback_days`.

    Each returned dict contains:
      {
        "filed":            "YYYY-MM-DD",
        "transaction_date": "YYYY-MM-DD",
        "transaction_type": "P" | "S" | "A" | "D" | ...,
        "shares":           float,
        "price_per_share":  float | None,
        "value_usd":        float | None,   # shares * price if both available
        "insider_name":     str,
        "form_type":        "4" | "4/A",
      }

    Returns empty list on any failure (EDGAR down, symbol not found, etc.).
    """
    cik = symbol_to_cik(symbol)
    if not cik:
        logger.debug("edgar_no_cik_for_symbol: %s", symbol)
        return []

    data = _fetch_submissions(cik)
    if not data:
        return []

    filings = data.get("filings", {}).get("recent", {})
    if not filings:
        return []

    # Parallel arrays in the SEC response — all same length
    form_types: List[str] = filings.get("form", [])
    filed_dates: List[str] = filings.get("filingDate", [])
    accession_nums: List[str] = filings.get("accessionNumber", [])

    cutoff = date.today() - timedelta(days=lookback_days)
    results: List[Dict[str, Any]] = []

    for i, form_type in enumerate(form_types):
        if form_type not in ("4", "4/A"):
            continue
        try:
            filed = date.fromisoformat(filed_dates[i])
        except (ValueError, IndexError):
            continue
        if filed < cutoff:
            continue

        # For a full implementation, parse the actual XML filing for share counts
        # and transaction type.  For Sprint 3 we return the filing metadata;
        # the score computation uses presence/absence + filing counts as proxy.
        results.append({
            "filed": str(filed),
            "transaction_date": str(filed),  # actual date is in the XML
            "transaction_type": "unknown",   # requires XML parse — Sprint 4
            "shares": None,
            "price_per_share": None,
            "value_usd": None,
            "insider_name": "",
            "form_type": form_type,
            "accession_number": accession_nums[i] if i < len(accession_nums) else "",
        })

    return results


def compute_insider_sentiment_score(
    symbol: str,
    lookback_days: int = 90,
) -> Dict[str, Any]:
    """
    Compute a net insider sentiment score for `symbol` in [-1, 1].

    Algorithm:
      - Fetch recent Form 4 filings within `lookback_days`.
      - Classify each as purchase (P) or sale (S) by transaction_type field.
        In Sprint 3 the XML is not yet parsed, so we use filing count as a
        proxy: each filing nudges the score +0.10 toward positive sentiment
        (insider activity of any kind is a mild positive signal vs no filings).
      - When transaction_type XML parsing is added in Sprint 4, the score will
        be computed as:
            score = (Σ purchase_value - Σ sale_value) / (Σ all_value + ε)

    Returns:
      {
        "symbol":         str,
        "score":          float in [-1, 1],  # 0.0 = neutral / no data
        "filing_count":   int,
        "lookback_days":  int,
        "method":         "filing_count_proxy" | "value_weighted",
        "transactions":   list,
      }
    """
    transactions = get_recent_form4_transactions(symbol, lookback_days)

    if not transactions:
        return {
            "symbol": symbol.upper(),
            "score": 0.0,
            "filing_count": 0,
            "lookback_days": lookback_days,
            "method": "no_data",
            "transactions": [],
        }

    # Classify by transaction_type once XML parsing is in place
    purchase_value = 0.0
    sale_value = 0.0
    for t in transactions:
        ttype = (t.get("transaction_type") or "").upper()
        val = t.get("value_usd") or 0.0
        if ttype == "P":
            purchase_value += val
        elif ttype == "S":
            sale_value += val

    total_value = purchase_value + sale_value
    if total_value > 0:
        # Value-weighted score: range [-1, 1]
        score = (purchase_value - sale_value) / (total_value + 1e-9)
        method = "value_weighted"
    else:
        # Proxy: each Form 4 filing = mild positive signal (capped at 0.5)
        # Rationale: insiders filing anything means active oversight, slightly
        # more informative than zero filings.  No directional info yet.
        filing_count = len(transactions)
        score = min(0.5, filing_count * 0.10)
        method = "filing_count_proxy"

    return {
        "symbol": symbol.upper(),
        "score": round(score, 4),
        "filing_count": len(transactions),
        "lookback_days": lookback_days,
        "method": method,
        "transactions": transactions[:20],  # cap for response size
    }
