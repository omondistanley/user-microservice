"""
Phase 5: Data retention purge job. Idempotent; supports dry-run.
Usage: python -m app.jobs.retention_purge --as-of YYYY-MM-DD [--dry-run]

Cross-database purges (investments_db, expenses_db on same Postgres host) are enabled when
RETENTION_PURGE_CROSS_DB is true (default). Set INVESTMENTS_DB_NAME / EXPENSE_DB_NAME if non-default.
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor

# Load config from same env as app
from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def _get_policies(conn):
    cur = conn.cursor()
    cur.execute(
        f'SELECT entity, retention_days, is_active FROM "{SCHEMA}".retention_policy WHERE is_active = TRUE'
    )
    return [dict(r) for r in cur.fetchall()]


def _purge_audit_log(conn, cutoff_ts, dry_run: bool):
    cur = conn.cursor()
    cur.execute(
        f'SELECT COUNT(*) AS c FROM "{SCHEMA}".audit_log WHERE created_at < %s',
        (cutoff_ts,),
    )
    count = cur.fetchone()["c"]
    if not dry_run and count > 0:
        cur.execute(f'DELETE FROM "{SCHEMA}".audit_log WHERE created_at < %s', (cutoff_ts,))
    return count


def _purge_password_reset_tokens(conn, cutoff_ts, dry_run: bool):
    cur = conn.cursor()
    cur.execute(
        f'SELECT COUNT(*) AS c FROM "{SCHEMA}".password_reset_token WHERE created_at < %s',
        (cutoff_ts,),
    )
    count = cur.fetchone()["c"]
    if not dry_run and count > 0:
        cur.execute(
            f'DELETE FROM "{SCHEMA}".password_reset_token WHERE created_at < %s',
            (cutoff_ts,),
        )
    return count


def _purge_user_notifications(conn, cutoff_ts, dry_run: bool):
    cur = conn.cursor()
    cur.execute(
        f'SELECT COUNT(*) AS c FROM "{SCHEMA}".user_notification WHERE created_at < %s',
        (cutoff_ts,),
    )
    count = cur.fetchone()["c"]
    if not dry_run and count > 0:
        cur.execute(
            f'DELETE FROM "{SCHEMA}".user_notification WHERE created_at < %s',
            (cutoff_ts,),
        )
    return count


def _purge_refresh_tokens(conn, cutoff_ts, dry_run: bool):
    """Purge revoked refresh tokens older than cutoff."""
    cur = conn.cursor()
    cur.execute(
        f'SELECT COUNT(*) AS c FROM "{SCHEMA}".refresh_token WHERE revoked_at IS NOT NULL AND revoked_at < %s',
        (cutoff_ts,),
    )
    count = cur.fetchone()["c"]
    if not dry_run and count > 0:
        cur.execute(
            f'DELETE FROM "{SCHEMA}".refresh_token WHERE revoked_at IS NOT NULL AND revoked_at < %s',
            (cutoff_ts,),
        )
    return count


def _open_named_db(dbname: str):
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=dbname,
        cursor_factory=RealDictCursor,
    )


def _purge_inv_recommendation_run(conn, cutoff_ts, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM investments_db.recommendation_run WHERE created_at < %s",
        (cutoff_ts,),
    )
    count = int(cur.fetchone()["c"])
    if not dry_run and count > 0:
        cur.execute(
            "DELETE FROM investments_db.recommendation_run WHERE created_at < %s",
            (cutoff_ts,),
        )
    return count


def _purge_inv_recommendation_digest(conn, cutoff_ts, dry_run: bool) -> int:
    cur = conn.cursor()
    d = cutoff_ts.date()
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM recommendation_digest
        WHERE created_at < %s OR week_start_date < %s
        """,
        (cutoff_ts, d),
    )
    count = int(cur.fetchone()["c"])
    if not dry_run and count > 0:
        cur.execute(
            "DELETE FROM recommendation_digest WHERE created_at < %s OR week_start_date < %s",
            (cutoff_ts, d),
        )
    return count


def _purge_inv_portfolio_health_snapshot(conn, cutoff_ts, dry_run: bool) -> int:
    cur = conn.cursor()
    d = cutoff_ts.date()
    cur.execute("SELECT COUNT(*) AS c FROM portfolio_health_snapshot WHERE snapshot_date < %s", (d,))
    count = int(cur.fetchone()["c"])
    if not dry_run and count > 0:
        cur.execute("DELETE FROM portfolio_health_snapshot WHERE snapshot_date < %s", (d,))
    return count


def _purge_inv_nudge_log(conn, cutoff_ts, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM nudge_log WHERE fired_at < %s", (cutoff_ts,))
    count = int(cur.fetchone()["c"])
    if not dry_run and count > 0:
        cur.execute("DELETE FROM nudge_log WHERE fired_at < %s", (cutoff_ts,))
    return count


def _purge_exp_anomaly_feedback(conn, cutoff_ts, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute(
        'SELECT COUNT(*) AS c FROM expenses_db.anomaly_feedback WHERE created_at < %s',
        (cutoff_ts,),
    )
    count = int(cur.fetchone()["c"])
    if not dry_run and count > 0:
        cur.execute('DELETE FROM expenses_db.anomaly_feedback WHERE created_at < %s', (cutoff_ts,))
    return count


def _purge_exp_classifier_correction(conn, cutoff_ts, dry_run: bool) -> int:
    cur = conn.cursor()
    cur.execute(
        'SELECT COUNT(*) AS c FROM expenses_db.classifier_correction WHERE created_at < %s',
        (cutoff_ts,),
    )
    count = int(cur.fetchone()["c"])
    if not dry_run and count > 0:
        cur.execute('DELETE FROM expenses_db.classifier_correction WHERE created_at < %s', (cutoff_ts,))
    return count


def _safe_cross_purge(label: str, fn, *args) -> int:
    try:
        return int(fn(*args))
    except pg_errors.UndefinedTable:
        return 0
    except Exception as exc:
        print(f"warning: {label}: {exc}", file=sys.stderr)
        return 0


def run(as_of: date, dry_run: bool):
    cross = os.environ.get("RETENTION_PURGE_CROSS_DB", "true").lower() in ("1", "true", "yes")
    inv_name = (os.environ.get("INVESTMENTS_DB_NAME") or "investments_db").strip()
    exp_name = (os.environ.get("EXPENSE_DB_NAME") or "expenses_db").strip()

    conn = _get_connection()
    inv_conn = None
    exp_conn = None
    try:
        conn.autocommit = False
        policies = _get_policies(conn)
        results: dict[str, int] = {}
        for pol in policies:
            entity = pol["entity"]
            days = int(pol["retention_days"])
            cutoff = datetime.combine(as_of - timedelta(days=days), datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
            if entity == "audit_log":
                results[entity] = _purge_audit_log(conn, cutoff, dry_run)
            elif entity == "password_reset_token":
                results[entity] = _purge_password_reset_tokens(conn, cutoff, dry_run)
            elif entity == "user_notification":
                results[entity] = _purge_user_notifications(conn, cutoff, dry_run)
            elif entity == "refresh_token":
                results[entity] = _purge_refresh_tokens(conn, cutoff, dry_run)
            elif cross and entity == "inv_recommendation_run":
                inv_conn = inv_conn or _open_named_db(inv_name)
                inv_conn.autocommit = False
                results[entity] = _safe_cross_purge(
                    entity, _purge_inv_recommendation_run, inv_conn, cutoff, dry_run
                )
            elif cross and entity == "inv_recommendation_digest":
                inv_conn = inv_conn or _open_named_db(inv_name)
                inv_conn.autocommit = False
                results[entity] = _safe_cross_purge(
                    entity, _purge_inv_recommendation_digest, inv_conn, cutoff, dry_run
                )
            elif cross and entity == "inv_portfolio_health_snapshot":
                inv_conn = inv_conn or _open_named_db(inv_name)
                inv_conn.autocommit = False
                results[entity] = _safe_cross_purge(
                    entity, _purge_inv_portfolio_health_snapshot, inv_conn, cutoff, dry_run
                )
            elif cross and entity == "inv_nudge_log":
                inv_conn = inv_conn or _open_named_db(inv_name)
                inv_conn.autocommit = False
                results[entity] = _safe_cross_purge(entity, _purge_inv_nudge_log, inv_conn, cutoff, dry_run)
            elif cross and entity == "exp_anomaly_feedback":
                exp_conn = exp_conn or _open_named_db(exp_name)
                exp_conn.autocommit = False
                results[entity] = _safe_cross_purge(
                    entity, _purge_exp_anomaly_feedback, exp_conn, cutoff, dry_run
                )
            elif cross and entity == "exp_classifier_correction":
                exp_conn = exp_conn or _open_named_db(exp_name)
                exp_conn.autocommit = False
                results[entity] = _safe_cross_purge(
                    entity, _purge_exp_classifier_correction, exp_conn, cutoff, dry_run
                )
            else:
                results[entity] = 0
        if not dry_run:
            conn.commit()
            if inv_conn:
                inv_conn.commit()
            if exp_conn:
                exp_conn.commit()
        else:
            conn.rollback()
            if inv_conn:
                inv_conn.rollback()
            if exp_conn:
                exp_conn.rollback()
        return results
    except Exception:
        conn.rollback()
        if inv_conn:
            inv_conn.rollback()
        if exp_conn:
            exp_conn.rollback()
        raise
    finally:
        conn.close()
        if inv_conn:
            inv_conn.close()
        if exp_conn:
            exp_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Retention purge job")
    parser.add_argument("--as-of", required=True, help="Reference date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Report counts only, do not delete")
    args = parser.parse_args()
    try:
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        print("Invalid --as-of; use YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    try:
        results = run(as_of, dry_run=args.dry_run)
        mode = " (dry-run)" if args.dry_run else ""
        print(f"Retention purge as-of {as_of}{mode}:")
        for entity, count in results.items():
            print(f"  {entity}: {count} rows")
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
