from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import json

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.core.config import RECOMMENDATIONS_DB_POOL_MAXCONN, RECOMMENDATIONS_DB_POOL_MINCONN

SCHEMA = "investments_db"
RUN_TABLE = "recommendation_run"
ITEM_TABLE = "recommendation_item"
_DB_POOL: Optional[ThreadedConnectionPool] = None


class RecommendationDataService:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def _get_connection(self):
        global _DB_POOL
        if _DB_POOL is None:
            _DB_POOL = ThreadedConnectionPool(
                RECOMMENDATIONS_DB_POOL_MINCONN,
                RECOMMENDATIONS_DB_POOL_MAXCONN,
                host=self.context["host"],
                port=self.context["port"],
                user=self.context["user"],
                password=self.context["password"],
                dbname=self.context["dbname"],
                cursor_factory=RealDictCursor,
            )
        return _DB_POOL.getconn()

    def _release_connection(self, conn) -> None:
        global _DB_POOL
        if _DB_POOL is not None and conn is not None:
            _DB_POOL.putconn(conn)

    def create_run(
        self,
        user_id: int,
        model_version: Optional[str],
        feature_snapshot_id: Optional[UUID],
        training_cutoff_date: Optional[datetime],
        notes: Optional[str],
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{RUN_TABLE}" '
                f"(user_id, model_version, feature_snapshot_id, training_cutoff_date, notes) "
                f"VALUES (%s, %s, %s, %s, %s) "
                f"RETURNING run_id, created_at",
                (user_id, model_version, feature_snapshot_id, training_cutoff_date, notes),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}
        finally:
            self._release_connection(conn)

    def insert_items(self, run_id: UUID, items: List[Dict[str, Any]]) -> None:
        if not items:
            return
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            for item in items:
                expl = item.get("explanation_json") or {}
                if isinstance(expl, dict):
                    expl = json.dumps(expl, default=str)
                cur.execute(
                    f'INSERT INTO "{SCHEMA}"."{ITEM_TABLE}" '
                    f"(run_id, symbol, score, confidence, explanation_json, created_at) "
                    f"VALUES (%s::uuid, %s, %s, %s, %s::jsonb, %s)",
                    (
                        str(run_id),
                        item["symbol"],
                        item["score"],
                        item.get("confidence"),
                        expl,
                        datetime.now(timezone.utc),
                    ),
                )
            conn.commit()
        finally:
            self._release_connection(conn)

    def get_latest_run(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{RUN_TABLE}" '
                f"WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._release_connection(conn)

    def get_run_for_user(self, run_id: UUID, user_id: int) -> Optional[Dict[str, Any]]:
        """Return run row only if it belongs to user_id (for explain API authorization)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{RUN_TABLE}" '
                f"WHERE run_id = %s::uuid AND user_id = %s",
                (str(run_id), user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._release_connection(conn)

    def update_run_portfolio_snapshot(self, run_id: UUID, portfolio: Dict[str, Any]) -> None:
        """Persist portfolio metrics for the run (column added in migration 014; no-op if missing)."""
        if not portfolio:
            return
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{RUN_TABLE}" '
                f"SET portfolio_snapshot = %s::jsonb WHERE run_id = %s::uuid",
                (json.dumps(portfolio, default=str), str(run_id)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            self._release_connection(conn)

    def update_run_artifacts(self, run_id: UUID, artifacts: Dict[str, Any]) -> None:
        if not artifacts:
            return
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{RUN_TABLE}" '
                f"SET run_artifacts = %s::jsonb WHERE run_id = %s::uuid",
                (json.dumps(artifacts, default=str), str(run_id)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            self._release_connection(conn)

    def list_items_for_run(self, run_id: UUID) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{ITEM_TABLE}" WHERE run_id = %s::uuid ORDER BY score DESC',
                (str(run_id),),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            self._release_connection(conn)

    def list_items_for_run_paginated(
        self, run_id: UUID, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return (items for page, total_count) for pagination."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT COUNT(*) FROM "{SCHEMA}"."{ITEM_TABLE}" WHERE run_id = %s::uuid',
                (str(run_id),),
            )
            total = cur.fetchone()["count"] or 0
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{ITEM_TABLE}" WHERE run_id = %s::uuid ORDER BY score DESC LIMIT %s OFFSET %s',
                (str(run_id), limit, offset),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows], total
        finally:
            self._release_connection(conn)

    def get_previous_run_for_user(self, run_id: UUID, user_id: int) -> Optional[Dict[str, Any]]:
        """Return previous run for the same user before given run_id by created_at."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT r2.*
                FROM "{SCHEMA}"."{RUN_TABLE}" r
                JOIN "{SCHEMA}"."{RUN_TABLE}" r2
                  ON r2.user_id = r.user_id
                 AND r2.created_at < r.created_at
                WHERE r.run_id = %s::uuid AND r.user_id = %s
                ORDER BY r2.created_at DESC
                LIMIT 1
                ''',
                (str(run_id), user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._release_connection(conn)

    def get_item_for_run_symbol(self, run_id: UUID, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{ITEM_TABLE}" WHERE run_id = %s::uuid AND symbol = %s LIMIT 1',
                (str(run_id), symbol.upper()),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._release_connection(conn)

    def list_recent_runs_for_user(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT run_id, created_at, model_version FROM "{SCHEMA}"."{RUN_TABLE}" '
                f"WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            self._release_connection(conn)

