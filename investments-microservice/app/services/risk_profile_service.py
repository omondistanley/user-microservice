from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor, Json

SCHEMA = "investments_db"
TABLE = "risk_profile"


class RiskProfileDataService:
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

    def get_risk_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def upsert_risk_profile(
        self,
        user_id: int,
        risk_tolerance: Optional[str] = None,
        horizon_years: Optional[int] = None,
        liquidity_needs: Optional[str] = None,
        target_volatility: Optional[float] = None,
        industry_preferences: Optional[List[str]] = None,
        sharpe_objective: Optional[float] = None,
        loss_aversion: Optional[str] = None,
        constraints_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Insert or update risk profile. Optional columns industry_preferences, sharpe_objective, loss_aversion (migration 003)."""
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            existing = self.get_risk_profile(user_id)
            updates = ["updated_at = now()"]
            vals: List[Any] = []
            if risk_tolerance is not None:
                updates.append("risk_tolerance = %s")
                vals.append(risk_tolerance)
            if horizon_years is not None:
                updates.append("horizon_years = %s")
                vals.append(horizon_years)
            if liquidity_needs is not None:
                updates.append("liquidity_needs = %s")
                vals.append(liquidity_needs)
            if target_volatility is not None:
                updates.append("target_volatility = %s")
                vals.append(target_volatility)
            if industry_preferences is not None:
                updates.append("industry_preferences = %s")
                vals.append(Json(industry_preferences if isinstance(industry_preferences, list) else []))
            if sharpe_objective is not None:
                updates.append("sharpe_objective = %s")
                vals.append(sharpe_objective)
            if loss_aversion is not None:
                updates.append("loss_aversion = %s")
                vals.append(loss_aversion)
            if constraints_json is not None:
                updates.append("constraints_json = %s")
                vals.append(Json(constraints_json))

            if existing:
                if not vals:
                    conn.rollback()
                    return dict(existing)
                vals.append(user_id)
                cur.execute(
                    f'UPDATE "{SCHEMA}"."{TABLE}" SET {", ".join(updates)} WHERE user_id = %s',
                    vals,
                )
                conn.commit()
                return dict(self.get_risk_profile(user_id) or existing)
            else:
                rt = risk_tolerance or "balanced"
                cur.execute(
                    f'INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, risk_tolerance, horizon_years, liquidity_needs, target_volatility, updated_at) '
                    "VALUES (%s, %s, %s, %s, %s, now()) ON CONFLICT (user_id) DO NOTHING",
                    (user_id, rt, horizon_years, liquidity_needs, target_volatility),
                )
                conn.commit()
                if vals:
                    vals.append(user_id)
                    cur.execute(
                        f'UPDATE "{SCHEMA}"."{TABLE}" SET {", ".join(updates)} WHERE user_id = %s',
                        vals,
                    )
                    conn.commit()
                out = self.get_risk_profile(user_id)
                return dict(out) if out else {"user_id": user_id, "risk_tolerance": rt}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

