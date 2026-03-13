from decimal import Decimal
from math import sqrt
from typing import Iterable, List, Tuple


def compute_returns(values: Iterable[Decimal]) -> List[Decimal]:
    seq = [Decimal(str(v)) for v in values]
    returns: List[Decimal] = []
    for i in range(1, len(seq)):
        prev = seq[i - 1]
        curr = seq[i]
        if prev == 0:
            returns.append(Decimal("0"))
        else:
            returns.append((curr - prev) / prev)
    return returns


def mean(values: Iterable[Decimal]) -> Decimal:
    vals = [Decimal(str(v)) for v in values]
    if not vals:
        return Decimal("0")
    return sum(vals) / Decimal(len(vals))


def stddev(values: Iterable[Decimal]) -> Decimal:
    vals = [Decimal(str(v)) for v in values]
    if len(vals) < 2:
        return Decimal("0")
    m = mean(vals)
    var = sum((v - m) * (v - m) for v in vals) / Decimal(len(vals) - 1)
    return Decimal(str(sqrt(float(var))))


def rolling_volatility_daily(returns: Iterable[Decimal]) -> Decimal:
    return stddev(returns)


def rolling_volatility_annualized(returns: Iterable[Decimal]) -> Decimal:
    daily = rolling_volatility_daily(returns)
    return Decimal(str(sqrt(252.0))) * daily


def max_drawdown(values: Iterable[Decimal]) -> Decimal:
    seq = [Decimal(str(v)) for v in values]
    if not seq:
        return Decimal("0")
    peak = seq[0]
    mdd = Decimal("0")
    for v in seq:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
    return mdd


def sharpe_ratio(returns: Iterable[Decimal], risk_free_annual: Decimal) -> Decimal:
    rets = [Decimal(str(v)) for v in returns]
    if not rets:
        return Decimal("0")
    rf_daily = risk_free_annual / Decimal("252")
    excess = [r - rf_daily for r in rets]
    avg_excess = mean(excess)
    vol_daily = rolling_volatility_daily(excess)
    if vol_daily == 0:
        return Decimal("0")
    return Decimal(str(sqrt(252.0))) * (avg_excess / vol_daily)


def concentration_metrics(weights: Iterable[Decimal]) -> Tuple[Decimal, Decimal, Decimal]:
    ws = sorted([abs(Decimal(str(w))) for w in weights], reverse=True)
    if not ws:
        return Decimal("0"), Decimal("0"), Decimal("0")
    top_1 = ws[0]
    top_3 = sum(ws[:3])
    hhi = sum(w * w for w in ws)
    return top_1, top_3, hhi

