"""
Scenario library: historical stress scenarios (asset-class return shocks).
Maps sector/style to impact bucket; loads from DB if table exists else built-in seed.
"""
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Sector (or style) -> scenario impact key (bucket)
SECTOR_TO_BUCKET = {
    "Technology": "growth_stocks",
    "Consumer Cyclical": "growth_stocks",
    "Communication Services": "growth_stocks",
    "Healthcare": "broad_equity",
    "Financial Services": "broad_equity",
    "Consumer Defensive": "defensive_equity",
    "Utilities": "defensive_equity",
    "Industrials": "broad_equity",
    "Basic Materials": "broad_equity",
    "Energy": "energy",
    "Real Estate": "real_estate",
    "Other": "broad_equity",
}


def get_bucket_for_sector(sector: str) -> str:
    """Map sector name to scenario impact bucket."""
    return SECTOR_TO_BUCKET.get((sector or "").strip(), "broad_equity")


# Built-in scenarios (historical asset-class return shocks, approximate)
BUILTIN_SCENARIOS = [
    {
        "id": "2008_crisis",
        "name": "2008 Financial Crisis",
        "impacts": {
            "growth_stocks": -0.45,
            "broad_equity": -0.38,
            "defensive_equity": -0.25,
            "energy": -0.35,
            "real_estate": -0.40,
            "long_bonds": 0.20,
        },
    },
    {
        "id": "2022_rate_hike",
        "name": "2022 Rate Hike / Drawdown",
        "impacts": {
            "growth_stocks": -0.32,
            "broad_equity": -0.18,
            "defensive_equity": -0.10,
            "energy": 0.04,
            "real_estate": -0.28,
            "long_bonds": -0.28,
        },
    },
    {
        "id": "covid_march_2020",
        "name": "COVID-19 March 2020",
        "impacts": {
            "growth_stocks": -0.25,
            "broad_equity": -0.22,
            "defensive_equity": -0.15,
            "energy": -0.40,
            "real_estate": -0.20,
            "long_bonds": 0.08,
        },
    },
]


def load_scenarios(context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Load scenarios from DB if table exists and has rows; else return built-in."""
    if context:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(
                host=context.get("host", "localhost"),
                port=int(context.get("port", 5432)),
                user=context.get("user", "postgres"),
                password=context.get("password", "postgres"),
                dbname=context.get("dbname", "investments_db"),
                cursor_factory=RealDictCursor,
            )
            cur = conn.cursor()
            cur.execute(
                'SELECT id, name, impacts_json FROM investments_db.scenario'
            )
            rows = cur.fetchall()
            conn.close()
            if rows:
                return [
                    {"id": r["id"], "name": r["name"], "impacts": r["impacts_json"] if isinstance(r["impacts_json"], dict) else json.loads(r["impacts_json"] or "{}")}
                    for r in rows
                ]
        except Exception as e:
            logger.debug("scenario_load_db_failed %s", e)
    return [{"id": s["id"], "name": s["name"], "impacts": s["impacts"]} for s in BUILTIN_SCENARIOS]
