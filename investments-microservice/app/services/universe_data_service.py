"""Security universe cache: list, get by symbol, upsert. Used by bootstrap and get_security_info."""
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "investments_db"
TABLE = "security_universe"


class UniverseDataService:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def _get_connection(self):
        return psycopg2.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            password=self.context["password"],
            dbname=self.context["dbname"],
            cursor_factory=RealDictCursor,
        )

    def list_universe(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return rows from security_universe, same shape as analyst universe (symbol, full_name, sector, risk_band, description, asset_type)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            sql = f'SELECT symbol, full_name, sector, risk_band, description, asset_type FROM "{SCHEMA}"."{TABLE}" ORDER BY symbol'
            if limit is not None and limit > 0:
                sql += " LIMIT %s"
                cur.execute(sql, (int(limit),))
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                # Normalize for engine: sector title case, risk_band/asset_type lower
                sector = (d.get("sector") or "broad_market").replace("_", " ").title()
                out.append({
                    "symbol": (d.get("symbol") or "").strip().upper(),
                    "full_name": d.get("full_name") or d.get("symbol"),
                    "sector": sector,
                    "risk_band": (d.get("risk_band") or "balanced").lower(),
                    "description": d.get("description") or "",
                    "asset_type": (d.get("asset_type") or "stock").lower(),
                })
            return out
        finally:
            conn.close()

    def get_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return one row as get_security_info shape: full_name, sector, description, asset_type, risk_band."""
        if not symbol or not isinstance(symbol, str):
            return None
        sym = symbol.strip().upper()
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT symbol, full_name, sector, risk_band, description, asset_type FROM "{SCHEMA}"."{TABLE}" WHERE symbol = %s',
                (sym,),
            )
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            sector = (d.get("sector") or "broad_market").replace("_", " ").title()
            return {
                "full_name": d.get("full_name") or d.get("symbol") or sym,
                "sector": sector,
                "description": d.get("description") or "",
                "asset_type": (d.get("asset_type") or "stock").lower(),
                "risk_band": (d.get("risk_band") or "balanced").lower(),
            }
        finally:
            conn.close()

    def upsert(
        self,
        symbol: str,
        full_name: str,
        sector: str,
        risk_band: str,
        description: str,
        asset_type: str,
        source_provider: str,
    ) -> None:
        """Insert or update one row. All strings; normalized in caller."""
        if not symbol:
            return
        sym = symbol.strip().upper()
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{TABLE}" '
                "(symbol, full_name, sector, risk_band, description, asset_type, source_provider, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, now()) "
                f'ON CONFLICT (symbol) DO UPDATE SET full_name = EXCLUDED.full_name, sector = EXCLUDED.sector, '
                'risk_band = EXCLUDED.risk_band, description = EXCLUDED.description, asset_type = EXCLUDED.asset_type, '
                'source_provider = EXCLUDED.source_provider, updated_at = now()',
                (sym, full_name or sym, sector or "broad_market", risk_band or "balanced", description or "", asset_type or "stock", source_provider or "on_demand"),
            )
            conn.commit()
        finally:
            conn.close()
