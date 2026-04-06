"""
AI Audit Log — append-only table for EU AI Act Article 13 transparency obligations.
Writes one row per recommendation run with hashed user_id, model_version, top reason,
and SHAP factor contributions vector (JSONB).

Table DDL (run once):
    CREATE TABLE IF NOT EXISTS investments_db.recommendation_audit_log (
        id              BIGSERIAL PRIMARY KEY,
        logged_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        user_id_hash    TEXT NOT NULL,          -- SHA-256 hex of str(user_id)
        run_id          TEXT,
        model_version   TEXT,
        top_reason      TEXT,
        shap_vector     JSONB,
        symbols         TEXT[],
        item_count      INT
    );
    CREATE INDEX IF NOT EXISTS idx_rec_audit_user ON investments_db.recommendation_audit_log (user_id_hash, logged_at DESC);
"""
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
TABLE = "recommendation_audit_log"


def _hash_user_id(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()


def write_audit_entry(
    context: Dict[str, Any],
    user_id: int,
    run_id: Optional[str],
    items: List[Dict[str, Any]],
) -> None:
    """
    Append one audit row. Called fire-and-forget from the recommendations router.
    Failures are logged but never re-raised so they cannot break the API response.
    """
    try:
        import psycopg2
        from psycopg2.extras import Json

        user_id_hash = _hash_user_id(user_id)
        model_version: Optional[str] = None
        top_reason: Optional[str] = None
        shap_vector: Optional[Dict[str, float]] = None
        symbols: List[str] = []

        for item in items[:20]:  # cap to first 20 for storage efficiency
            sym = str(item.get("symbol") or "")
            if sym:
                symbols.append(sym)
            # Extract model_version and SHAP from first scored item
            if model_version is None:
                sb = item.get("score_breakdown") or {}
                mv = sb.get("model_version") or item.get("model_version")
                if mv:
                    model_version = str(mv)
                fc = sb.get("factor_contributions") or item.get("factor_contributions")
                if fc and isinstance(fc, dict) and shap_vector is None:
                    shap_vector = {k: float(v) for k, v in fc.items() if isinstance(v, (int, float))}
            if top_reason is None:
                tr = item.get("why_shown_one_line") or item.get("top_reason")
                if tr:
                    top_reason = str(tr)[:500]

        conn = psycopg2.connect(
            host=context.get("host", "localhost"),
            port=int(context.get("port", 5432)),
            user=context.get("user", "postgres"),
            password=context.get("password", "postgres"),
            dbname=context.get("dbname", "investments_db"),
        )
        conn.autocommit = True
        try:
            cur = conn.cursor()
            # Ensure table exists (idempotent)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS "{SCHEMA}"."{TABLE}" (
                    id              BIGSERIAL PRIMARY KEY,
                    logged_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                    user_id_hash    TEXT NOT NULL,
                    run_id          TEXT,
                    model_version   TEXT,
                    top_reason      TEXT,
                    shap_vector     JSONB,
                    symbols         TEXT[],
                    item_count      INT
                )
            """)
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{TABLE}" '
                "(user_id_hash, run_id, model_version, top_reason, shap_vector, symbols, item_count) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id_hash,
                    run_id,
                    model_version,
                    top_reason,
                    Json(shap_vector) if shap_vector else None,
                    symbols,
                    len(items),
                ),
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("AI audit log write failed (non-fatal): %s", exc)
