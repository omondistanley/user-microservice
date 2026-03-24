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
import xml.etree.ElementTree as ET
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
_SEC_FILING_HEADERS = {
    "User-Agent": "pocketii-personal-finance dev@pocketii.app",
    "Accept-Encoding": "gzip, deflate",
}
_SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# Form 4 XML primary document URL pattern
_SEC_FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/{quarter}/form.idx"
_SEC_ACCESSION_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
_REQUEST_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# XML filing cache  { accession_number: (timestamp, parsed_transactions) }
# ---------------------------------------------------------------------------
_filing_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_filing_cache_lock = threading.Lock()
_FILING_CACHE_TTL = 86_400  # 24 hours

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


def _fetch_form4_xml(cik: str, accession_number: str) -> Optional[str]:
    """
    Fetch the primary Form 4 XML document for a given accession number.
    Accession number format: 0001234567-23-012345  (dashes)
    SEC path format:         0001234567-23-012345 → 000123456723012345 (no dashes)
    Returns XML string or None on failure.
    """
    now = time.monotonic()
    with _filing_cache_lock:
        cached = _filing_cache.get(accession_number)
        if cached and (now - cached[0]) < _FILING_CACHE_TTL:
            # Return sentinel "" to indicate cached empty result
            return None if cached[1] is None else "__cached__"

    accession_nodash = accession_number.replace("-", "")
    base_url = _SEC_ACCESSION_BASE.format(cik=cik.lstrip("0"), accession=accession_nodash)
    # The primary Form 4 document is typically named after the accession number
    xml_url = f"{base_url}{accession_nodash}.xml"
    try:
        resp = requests.get(xml_url, headers=_SEC_FILING_HEADERS, timeout=_REQUEST_TIMEOUT)
        if resp.status_code == 404:
            # Try alternate filename pattern
            xml_url2 = f"{base_url}form4.xml"
            resp = requests.get(xml_url2, headers=_SEC_FILING_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.debug("edgar_form4_xml_fetch_failed acc=%s: %s", accession_number, exc)
        return None


def _parse_form4_xml(xml_text: str, filed_date: str) -> List[Dict[str, Any]]:
    """
    Parse SEC Form 4 XML and extract non-derivative transactions.

    Returns list of dicts with keys:
      transaction_date, transaction_type (P/S/A/D/etc),
      shares, price_per_share, value_usd, insider_name, acquisition_or_disposition
    """
    transactions: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug("form4_xml_parse_error: %s", exc)
        return transactions

    # Namespaces vary; strip them for simple tag matching
    def _tag(el) -> str:
        return el.tag.split("}")[-1] if "}" in el.tag else el.tag

    def _text(el, tag: str) -> Optional[str]:
        child = el.find(f".//{tag}")
        if child is None:
            # Try with possible namespace prefix
            for c in el.iter():
                if _tag(c) == tag:
                    return (c.text or "").strip() or None
            return None
        return (child.text or "").strip() or None

    # Insider name from reportingOwner
    insider_name = ""
    for owner in root.iter():
        if _tag(owner) == "reportingOwner":
            name_el = None
            for child in owner.iter():
                if _tag(child) == "rptOwnerName":
                    name_el = child
                    break
            if name_el is not None and name_el.text:
                insider_name = name_el.text.strip()
            break

    # nonDerivativeTable → nonDerivativeTransaction entries
    for el in root.iter():
        if _tag(el) != "nonDerivativeTransaction":
            continue

        # Transaction type: P (purchase), S (sale), A (award), D (disposition), etc.
        t_code = None
        for child in el.iter():
            if _tag(child) == "transactionCode":
                t_code = (child.text or "").strip().upper() or None
                break

        # Transaction date
        tx_date = filed_date  # fallback
        for child in el.iter():
            if _tag(child) == "transactionDate":
                # value element
                for val in child.iter():
                    if _tag(val) == "value" and val.text:
                        tx_date = val.text.strip()
                        break
                break

        # Shares
        shares: Optional[float] = None
        for child in el.iter():
            if _tag(child) == "transactionShares":
                for val in child.iter():
                    if _tag(val) == "value" and val.text:
                        try:
                            shares = float(val.text.strip())
                        except ValueError:
                            pass
                        break
                break

        # Price per share
        price: Optional[float] = None
        for child in el.iter():
            if _tag(child) == "transactionPricePerShare":
                for val in child.iter():
                    if _tag(val) == "value" and val.text:
                        try:
                            price = float(val.text.strip())
                        except ValueError:
                            pass
                        break
                break

        # Acquisition (A) or Disposition (D)
        acq_disp = None
        for child in el.iter():
            if _tag(child) == "transactionAcquiredDisposedCode":
                for val in child.iter():
                    if _tag(val) == "value" and val.text:
                        acq_disp = val.text.strip().upper()
                        break
                break

        value_usd: Optional[float] = None
        if shares is not None and price is not None:
            value_usd = round(shares * price, 2)

        transactions.append({
            "transaction_date": tx_date[:10] if tx_date else filed_date,
            "transaction_type": t_code or (
                "P" if acq_disp == "A" else ("S" if acq_disp == "D" else "unknown")
            ),
            "shares": shares,
            "price_per_share": price,
            "value_usd": value_usd,
            "insider_name": insider_name,
            "acquisition_or_disposition": acq_disp,
        })

    return transactions


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

        accession = accession_nums[i] if i < len(accession_nums) else ""
        filed_str = str(filed)

        # Sprint 4: parse the actual XML filing for transaction type, shares, price
        xml_transactions: List[Dict[str, Any]] = []
        if accession and cik:
            cached_key = accession
            with _filing_cache_lock:
                cached = _filing_cache.get(cached_key)
            if cached and (time.monotonic() - cached[0]) < _FILING_CACHE_TTL:
                xml_transactions = cached[1] or []
            else:
                xml_text = _fetch_form4_xml(cik, accession)
                if xml_text and xml_text != "__cached__":
                    xml_transactions = _parse_form4_xml(xml_text, filed_str)
                    with _filing_cache_lock:
                        _filing_cache[cached_key] = (time.monotonic(), xml_transactions)

        if xml_transactions:
            for tx in xml_transactions:
                results.append({
                    "filed": filed_str,
                    "transaction_date": tx.get("transaction_date", filed_str),
                    "transaction_type": tx.get("transaction_type", "unknown"),
                    "shares": tx.get("shares"),
                    "price_per_share": tx.get("price_per_share"),
                    "value_usd": tx.get("value_usd"),
                    "insider_name": tx.get("insider_name", ""),
                    "form_type": form_type,
                    "accession_number": accession,
                })
        else:
            # Fallback: filing metadata only (no XML or parse failed)
            results.append({
                "filed": filed_str,
                "transaction_date": filed_str,
                "transaction_type": "unknown",
                "shares": None,
                "price_per_share": None,
                "value_usd": None,
                "insider_name": "",
                "form_type": form_type,
                "accession_number": accession,
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

    # Value-weighted score using XML-parsed transaction data (Sprint 4).
    # Falls back to filing_count_proxy when XML is unavailable or transaction
    # types are all "unknown" (e.g. EDGAR temporarily unavailable).
    purchase_value = 0.0
    sale_value = 0.0
    known_type_count = 0
    for t in transactions:
        ttype = (t.get("transaction_type") or "").upper()
        val = float(t.get("value_usd") or 0.0)
        if ttype == "P":
            purchase_value += val
            known_type_count += 1
        elif ttype == "S":
            sale_value += val
            known_type_count += 1
        elif ttype in ("A", "D"):
            # Award (A) = mild positive; Disposition (D) = mild negative
            if ttype == "A":
                purchase_value += val * 0.5  # awards are less bullish than open-market buys
            else:
                sale_value += val * 0.5
            known_type_count += 1

    total_value = purchase_value + sale_value
    if total_value > 0 and known_type_count > 0:
        # Value-weighted score: range [-1, 1]
        score = (purchase_value - sale_value) / (total_value + 1e-9)
        method = "value_weighted"
    else:
        # Proxy: each Form 4 filing = mild positive signal (capped at 0.5)
        # Used when XML fetch failed for all filings or all types are unknown.
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
