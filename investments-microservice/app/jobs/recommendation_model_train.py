"""
Offline trainer for quant recommendation ranker artifact.

Usage:
  python -m app.jobs.recommendation_model_train
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from app.core.config import (
    RISK_FREE_RATE_ANNUAL,
    RECOMMENDATIONS_QUANT_MODEL_PATH,
    RECOMMENDATIONS_QUANT_MODEL_VERSION,
)
from app.services.analytics_math import (
    concentration_metrics,
    compute_returns,
    max_drawdown,
    rolling_volatility_annualized,
    sharpe_ratio,
)
from app.services.holdings_data_service import HoldingsDataService
from app.services.portfolio_snapshot_service import PortfolioSnapshotDataService
from app.services.quant_model_service import save_artifact, train_quant_ranker
from app.services.recommendation_feature_contract import build_feature_row
from app.services.service_factory import ServiceFactory


def _get_holdings_service() -> HoldingsDataService:
    svc = ServiceFactory.get_service("HoldingsDataService")
    assert isinstance(svc, HoldingsDataService)
    return svc


def _get_snapshot_service() -> PortfolioSnapshotDataService:
    svc = ServiceFactory.get_service("PortfolioSnapshotDataService")
    assert isinstance(svc, PortfolioSnapshotDataService)
    return svc


def _training_rows_for_user(user_id: int) -> List[Dict[str, Any]]:
    holdings_svc = _get_holdings_service()
    snapshot_svc = _get_snapshot_service()
    holdings_rows = holdings_svc.list_all_holdings_for_user(user_id)
    if not holdings_rows:
        return []
    snapshot = snapshot_svc.get_latest_snapshot(user_id)
    if snapshot:
        total_value = Decimal(str(snapshot.get("total_value") or "0"))
        total_cost = Decimal(str(snapshot.get("total_cost_basis") or "0"))
    else:
        total_value = sum(
            Decimal(str(r.get("quantity") or "0")) * Decimal(str(r.get("avg_cost") or "0"))
            for r in holdings_rows
        )
        total_cost = total_value
    values = [
        Decimal(str(r.get("quantity") or "0")) * Decimal(str(r.get("avg_cost") or "0"))
        for r in holdings_rows
    ]
    weights = [v / total_value for v in values] if total_value > 0 else [Decimal("0")] * len(values)
    _, _, hhi = concentration_metrics(weights)
    history = snapshot_svc.list_snapshots(user_id, date_from=date.today() - timedelta(days=365))
    if len(history) >= 3:
        pv = [Decimal(str(r["total_value"])) for r in history]
    else:
        pv = [total_cost, total_value]
    returns = compute_returns(pv)
    vol = rolling_volatility_annualized(returns)
    shp = sharpe_ratio(returns, Decimal(str(RISK_FREE_RATE_ANNUAL)))
    rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(holdings_rows):
        w = weights[idx] if idx < len(weights) else Decimal("0")
        base = shp if shp > 0 else Decimal("0")
        weight_penalty = (w - Decimal("0.2")) * Decimal("2") if w > Decimal("0.2") else Decimal("0")
        heuristic = max(Decimal("0"), base - weight_penalty)
        rows.append(
            build_feature_row(
                symbol=str(row.get("symbol") or "").upper(),
                heuristic_score=float(heuristic),
                weight=float(w),
                vol_annual=float(vol),
                hhi=float(hhi),
                tlh_loss_scaled=0.0,
            ).to_dict()
        )
    return rows


def main() -> None:
    holdings_svc = _get_holdings_service()
    user_ids = holdings_svc.list_distinct_user_ids(limit=5000)
    rows: List[Dict[str, Any]] = []
    for uid in user_ids:
        rows.extend(_training_rows_for_user(uid))
    artifact = train_quant_ranker(rows, RECOMMENDATIONS_QUANT_MODEL_VERSION)
    save_artifact(RECOMMENDATIONS_QUANT_MODEL_PATH, artifact)
    print(
        f"trained {artifact.model_version} samples={artifact.backtest.get('samples', 0)} "
        f"r2={artifact.backtest.get('r2', 0)} mae={artifact.backtest.get('mae', 0)} "
        f"path={RECOMMENDATIONS_QUANT_MODEL_PATH}"
    )


if __name__ == "__main__":
    main()
