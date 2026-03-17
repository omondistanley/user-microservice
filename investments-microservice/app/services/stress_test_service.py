"""
Historical scenario stress testing: apply asset-class return shocks to portfolio (post look-through).
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from app.services.scenario_library import get_bucket_for_sector, load_scenarios


def run_stress_test(
    context: Dict[str, Any],
    positions_by_sector: List[Dict[str, Any]],
    total_value: float,
) -> List[Dict[str, Any]]:
    """
    positions_by_sector: list of { "sector": str, "value": float } (e.g. from look-through + sector).
    total_value: portfolio total market value.
    Returns list of { scenario_id, scenario_name, projected_return_pct, dollar_impact, projected_value }.
    """
    if total_value <= 0:
        return []
    # Weights by bucket (sector -> bucket, then aggregate value by bucket)
    bucket_values: Dict[str, float] = defaultdict(float)
    for p in positions_by_sector:
        sector = p.get("sector") or p.get("name") or "Other"
        val = p.get("value") or 0
        if isinstance(val, Decimal):
            val = float(val)
        bucket = get_bucket_for_sector(sector)
        bucket_values[bucket] += val
    bucket_weights = {b: v / total_value for b, v in bucket_values.items()}
    scenarios = load_scenarios(context)
    results = []
    for sc in scenarios:
        impacts = sc.get("impacts") or {}
        projected_return = sum(
            bucket_weights.get(bucket, 0) * impacts.get(bucket, 0)
            for bucket in bucket_weights
        )
        dollar_impact = total_value * projected_return
        projected_value = total_value + dollar_impact
        results.append({
            "scenario_id": sc.get("id"),
            "scenario_name": sc.get("name"),
            "projected_return_pct": round(projected_return * 100, 2),
            "dollar_impact": round(dollar_impact, 2),
            "projected_value": round(projected_value, 2),
        })
    return results
