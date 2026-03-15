"""
Rolling correlation matrix of daily returns; diversification score; high-correlation pairs; marginal contribution.
"""
import logging
from typing import Any, Dict, List, Tuple

import numpy as np

from app.services.daily_returns_service import get_returns_matrix

logger = logging.getLogger(__name__)

HIGH_CORRELATION_THRESHOLD = 0.8


def _align_returns(matrix: Dict[str, List[float]]) -> Tuple[List[str], np.ndarray]:
    """
    Align to common length (min length across symbols); return (symbols, np array of shape (n_symbols, n_days)).
    Drops symbols with no data.
    """
    valid = {s: r for s, r in matrix.items() if r and len(r) >= 2}
    if not valid:
        return [], np.array([])
    min_len = min(len(r) for r in valid.values())
    symbols = list(valid.keys())
    arr = np.array([valid[s][-min_len:] for s in symbols], dtype=float)
    return symbols, arr


def correlation_matrix_from_returns(
    symbols: List[str],
    returns_matrix: Dict[str, List[float]],
) -> Dict[str, Any]:
    """
    Compute Pearson correlation matrix, diversification score, high-correlation pairs, and per-symbol marginal.
    returns_matrix: symbol -> list of daily return %.
    """
    sym_list, arr = _align_returns(returns_matrix)
    if arr.size == 0 or len(sym_list) < 2:
        return {
            "symbols": sym_list,
            "matrix": {},
            "high_correlation_pairs": [],
            "diversification_score": 0.0,
            "per_symbol_marginal": {},
        }
    # Pearson correlation
    corr = np.corrcoef(arr)
    if corr is None or corr.ndim < 2:
        return {
            "symbols": sym_list,
            "matrix": {},
            "high_correlation_pairs": [],
            "diversification_score": 0.0,
            "per_symbol_marginal": {},
        }
    # Build matrix dict: (sym_i, sym_j) -> correlation (upper triangle only to avoid duplicate)
    matrix_dict = {}
    for i, si in enumerate(sym_list):
        for j, sj in enumerate(sym_list):
            if i <= j:
                matrix_dict[f"{si}_{sj}"] = round(float(corr[i, j]), 4)
    # High correlation pairs (excluding diagonal)
    high_pairs = []
    for i in range(len(sym_list)):
        for j in range(i + 1, len(sym_list)):
            c = corr[i, j]
            if not np.isnan(c) and abs(c) >= HIGH_CORRELATION_THRESHOLD:
                high_pairs.append({
                    "symbol_1": sym_list[i],
                    "symbol_2": sym_list[j],
                    "correlation": round(float(c), 4),
                })
    # Diversification score: 1 - mean(abs(correlation)) excluding diagonal
    off_diag = []
    for i in range(len(sym_list)):
        for j in range(len(sym_list)):
            if i != j and not np.isnan(corr[i, j]):
                off_diag.append(abs(corr[i, j]))
    avg_corr = np.mean(off_diag) if off_diag else 0.0
    div_score = round(1.0 - avg_corr, 4)
    # Per-symbol marginal: diversification score when excluding that symbol
    marginal = {}
    for drop in range(len(sym_list)):
        keep = [x for x in range(len(sym_list)) if x != drop]
        if len(keep) < 2:
            marginal[sym_list[drop]] = 0.0
            continue
        sub = arr[keep]
        sub_corr = np.corrcoef(sub)
        if sub_corr is not None and sub_corr.ndim == 2:
            off = []
            for i in range(len(keep)):
                for j in range(len(keep)):
                    if i != j and not np.isnan(sub_corr[i, j]):
                        off.append(abs(sub_corr[i, j]))
            sub_avg = np.mean(off) if off else 0.0
            marginal[sym_list[drop]] = round(1.0 - sub_avg, 4)
        else:
            marginal[sym_list[drop]] = 0.0
    return {
        "symbols": sym_list,
        "matrix": matrix_dict,
        "high_correlation_pairs": high_pairs,
        "diversification_score": div_score,
        "per_symbol_marginal": marginal,
    }


def get_correlation_analysis(
    context: Dict[str, Any],
    symbols: List[str],
    days: int = 90,
    backfill: bool = True,
) -> Dict[str, Any]:
    """
    Get returns matrix for symbols, then compute correlation analysis.
    """
    if not symbols:
        return {
            "symbols": [],
            "matrix": {},
            "high_correlation_pairs": [],
            "diversification_score": 0.0,
            "per_symbol_marginal": {},
        }
    matrix = get_returns_matrix(context, symbols, days=days, backfill_if_missing=backfill)
    return correlation_matrix_from_returns(symbols, matrix)
