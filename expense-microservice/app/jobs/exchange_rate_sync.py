import argparse
import csv
import json
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
logger = logging.getLogger("expense_exchange_rate_sync")


def _configure_logging(level: str) -> None:
    resolved_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(level=resolved_level, format="%(message)s")


def _log_json(level: str, **fields: Any) -> None:
    line = json.dumps(fields, default=str, separators=(",", ":"))
    if level == "error":
        logger.error(line)
    else:
        logger.info(line)


def _parse_date(value: Optional[str]) -> date:
    if not value:
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid --date '{value}': {e}") from e


def _get_data_service() -> ExpenseDataService:
    service = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(service, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return service


def _load_eur_rates_from_csv(path: Path) -> Dict[str, Decimal]:
    rates: Dict[str, Decimal] = {"EUR": Decimal("1")}
    with path.open("r", encoding="utf-8") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        has_header = "currency" in sample.lower() and "rate" in sample.lower()
        if has_header:
            reader = csv.DictReader(fh)
            for row in reader:
                currency = str(row.get("currency") or "").strip().upper()
                rate_raw = row.get("rate")
                if not currency or not rate_raw:
                    continue
                rates[currency] = Decimal(str(rate_raw))
        else:
            reader = csv.reader(fh)
            for row in reader:
                if len(row) < 2:
                    continue
                currency = str(row[0]).strip().upper()
                if not currency:
                    continue
                rates[currency] = Decimal(str(row[1]).strip())
    return rates


def _extract_best_cube(root: ET.Element, target_date: date) -> Optional[ET.Element]:
    cubes = root.findall(".//{*}Cube[@time]")
    if not cubes:
        return None
    target_iso = target_date.isoformat()
    exact = None
    prior: list[tuple[date, ET.Element]] = []
    for cube in cubes:
        t = cube.attrib.get("time")
        if not t:
            continue
        try:
            d = date.fromisoformat(t)
        except ValueError:
            continue
        if d == target_date:
            exact = cube
            break
        if d <= target_date:
            prior.append((d, cube))
    if exact is not None:
        return exact
    if prior:
        prior.sort(key=lambda x: x[0], reverse=True)
        return prior[0][1]
    return None


def _load_eur_rates_from_ecb(target_date: date) -> tuple[date, Dict[str, Decimal]]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(ECB_HIST_URL)
        resp.raise_for_status()
        content = resp.text
    root = ET.fromstring(content)
    cube = _extract_best_cube(root, target_date)
    if cube is None:
        raise RuntimeError("No exchange-rate cube found in ECB payload")
    used_date = date.fromisoformat(cube.attrib["time"])
    rates: Dict[str, Decimal] = {"EUR": Decimal("1")}
    for child in list(cube):
        currency = str(child.attrib.get("currency") or "").strip().upper()
        rate_raw = child.attrib.get("rate")
        if not currency or not rate_raw:
            continue
        rates[currency] = Decimal(str(rate_raw))
    if len(rates) <= 1:
        raise RuntimeError("ECB payload did not include rates")
    return used_date, rates


def _build_cross_rates(eur_rates: Dict[str, Decimal]) -> list[dict[str, Any]]:
    currencies = sorted(eur_rates.keys())
    out: list[dict[str, Any]] = []
    for base in currencies:
        base_factor = eur_rates[base]
        if base_factor <= 0:
            continue
        for quote in currencies:
            quote_factor = eur_rates[quote]
            if quote_factor <= 0:
                continue
            rate = (quote_factor / base_factor).quantize(Decimal("0.0000000001"))
            out.append(
                {
                    "base_currency": base,
                    "quote_currency": quote,
                    "rate": rate,
                }
            )
    return out


def run_exchange_rate_sync(
    target_date: date,
    source: str = "ECB",
    csv_path: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    request_id = str(job_id or uuid.uuid4())
    service = _get_data_service()

    if csv_path:
        path = Path(csv_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        eur_rates = _load_eur_rates_from_csv(path)
        used_date = target_date
        source_name = "CSV"
    else:
        used_date, eur_rates = _load_eur_rates_from_ecb(target_date)
        source_name = source

    rates = _build_cross_rates(eur_rates)
    upsert_result = service.upsert_exchange_rates(
        rate_date=used_date,
        source=source_name,
        rates=rates,
    )
    result = {
        "job_id": request_id,
        "requested_date": target_date.isoformat(),
        "rate_date": used_date.isoformat(),
        "source": source_name,
        "fetched_count": len(rates),
        "upserted_count": int(upsert_result.get("upserted_count", 0)),
        "failed_count": int(upsert_result.get("failed_count", 0)),
    }
    _log_json("info", service="expense", component="exchange_rate_sync", **result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync exchange rates into expenses_db.exchange_rate.")
    parser.add_argument("--date", default=None, help="Target date (YYYY-MM-DD). Defaults to today UTC.")
    parser.add_argument("--source", default="ECB", help="Rate source label. Default: ECB.")
    parser.add_argument("--csv", default=None, help="Optional CSV fallback path (currency,rate).")
    parser.add_argument("--job-id", default=None, help="Optional correlation id for logs.")
    parser.add_argument("--log-level", default="INFO", help="DEBUG|INFO|WARNING|ERROR")
    args = parser.parse_args()

    _configure_logging(args.log_level)
    target_date = _parse_date(args.date)
    result = run_exchange_rate_sync(
        target_date=target_date,
        source=args.source,
        csv_path=args.csv,
        job_id=args.job_id,
    )
    return 1 if int(result.get("failed_count", 0)) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
