from decimal import Decimal

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.analytics_math import (  # type: ignore[attr-defined]
    compute_returns,
    concentration_metrics,
    max_drawdown,
    rolling_volatility_annualized,
    sharpe_ratio,
)


def test_compute_returns_basic():
    values = [Decimal("100"), Decimal("110"), Decimal("99")]
    rets = compute_returns(values)
    assert len(rets) == 2
    assert rets[0] == Decimal("0.10")
    # second return: (99-110)/110 = -0.1
    assert rets[1].quantize(Decimal("0.0001")) == Decimal("-0.1000")


def test_max_drawdown():
    # values go 100 -> 120 -> 90 -> 130; max dd is (120-90)/120 = 0.25
    values = [Decimal("100"), Decimal("120"), Decimal("90"), Decimal("130")]
    mdd = max_drawdown(values)
    assert mdd.quantize(Decimal("0.0001")) == Decimal("0.2500")


def test_concentration_metrics():
    weights = [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]
    top1, top3, hhi = concentration_metrics(weights)
    assert top1 == Decimal("0.5")
    assert top3 == Decimal("1.0")
    assert hhi.quantize(Decimal("0.0001")) == Decimal("0.3800")


def test_sharpe_and_volatility_non_zero():
    values = [Decimal("100"), Decimal("105"), Decimal("110"), Decimal("100")]
    rets = compute_returns(values)
    vol = rolling_volatility_annualized(rets)
    assert vol > 0
    sr = sharpe_ratio(rets, Decimal("0.02"))
    # we only assert it's a finite Decimal (no crash / div by zero)
    assert isinstance(sr, Decimal)

