"""
Phase 5: Data retention purge job. Idempotent; supports dry-run.
Usage: python -m app.jobs.retention_purge --as-of YYYY-MM-DD [--dry-run]
"""
import argparse
import sys
from datetime import date, datetime, timedelta, timezone

import psycopg2
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


def run(as_of: date, dry_run: bool):
    conn = _get_connection()
    try:
        conn.autocommit = False
        policies = _get_policies(conn)
        results = {}
        for pol in policies:
            entity = pol["entity"]
            days = int(pol["retention_days"])
            cutoff = datetime.combine(as_of - timedelta(days=days), datetime.min.time()).replace(tzinfo=timezone.utc)
            if entity == "audit_log":
                results[entity] = _purge_audit_log(conn, cutoff, dry_run)
            elif entity == "password_reset_token":
                results[entity] = _purge_password_reset_tokens(conn, cutoff, dry_run)
            elif entity == "user_notification":
                results[entity] = _purge_user_notifications(conn, cutoff, dry_run)
            elif entity == "refresh_token":
                results[entity] = _purge_refresh_tokens(conn, cutoff, dry_run)
            else:
                results[entity] = 0
        if not dry_run:
            conn.commit()
        else:
            conn.rollback()
        return results
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
