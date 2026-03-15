from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import json

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "investments_db"
RUN_TABLE = "recommendation_run"
ITEM_TABLE = "recommendation_item"


class RecommendationDataService:
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
            conn.close()

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
            conn.close()

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
            conn.close()

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
            conn.close()

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
            conn.close()

