#!/usr/bin/env python3
"""
Run a single migration only if not already applied (idempotent across deploys).
Uses DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME from env.
Creates public.schema_migrations (filename, applied_at) per database and skips
migrations that are already recorded.

Usage: python run_migration_tracked.py <path_to_migration.sql>
Example: python run_migration_tracked.py /opt/expense/migrations/001_schema.sql
"""
import os
import sys
from pathlib import Path

import psycopg2

DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "users_db")

TABLE = "public.schema_migrations"


def parse_statements(sql: str):
    """Split SQL into statements, stripping leading full-line comments per chunk."""
    statements = []
    for s in sql.split(";"):
        s = s.strip()
        if not s:
            continue
        lines = s.split("\n")
        while lines and lines[0].strip().startswith("--"):
            lines.pop(0)
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


def main():
    if len(sys.argv) < 2:
        print("Usage: run_migration_tracked.py <path_to_migration.sql>", file=sys.stderr)
        sys.exit(1)

    migration_path = Path(sys.argv[1])
    if not migration_path.exists():
        print(f"Migration not found: {migration_path}", file=sys.stderr)
        sys.exit(1)

    filename = migration_path.name

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=int(DB_PORT),
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Ensure tracking table exists
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )

        # Skip if already applied
        cur.execute("SELECT 1 FROM public.schema_migrations WHERE filename = %s", (filename,))
        if cur.fetchone():
            print(f"skip (already applied): {filename}")
            cur.close()
            conn.close()
            return

        sql = migration_path.read_text()
        statements = parse_statements(sql)

        for stmt in statements:
            if stmt:
                cur.execute(stmt)
                preview = stmt[:60].replace("\n", " ") + "..." if len(stmt) > 60 else stmt
                print("OK:", preview)

        cur.execute("INSERT INTO public.schema_migrations (filename) VALUES (%s)", (filename,))
        print(f"recorded: {filename}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
