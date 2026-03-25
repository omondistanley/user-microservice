#!/usr/bin/env python3
"""
Run migrations. Uses same DB config as the app (env or defaults).
Usage: python run_migration.py [migration_file]
Default: migrations/001_schema.sql
"""
import os
import sys
from pathlib import Path

import psycopg2

DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", os.environ.get("INVESTMENTS_DB_NAME", "investments_db"))


def main():
    root = Path(__file__).resolve().parent
    default_migration = "migrations/001_schema.sql"
    migration = root / (sys.argv[1] if len(sys.argv) > 1 else default_migration)
    if not migration.exists():
        print(f"Migration not found: {migration}")
        sys.exit(1)

    sql = migration.read_text()

    def _split_sql(text: str) -> list:
        """Split SQL on semicolons while respecting dollar-quoted blocks ($$...$$)."""
        statements = []
        current = []
        in_dollar_quote = False
        dollar_tag = ""
        i = 0
        while i < len(text):
            if text[i] == "$":
                j = text.index("$", i + 1) if "$" in text[i + 1:] else -1
                if j != -1:
                    tag = text[i:j + 1]
                    if not in_dollar_quote:
                        in_dollar_quote = True
                        dollar_tag = tag
                        current.append(text[i:j + 1])
                        i = j + 1
                        continue
                    elif tag == dollar_tag:
                        in_dollar_quote = False
                        dollar_tag = ""
                        current.append(text[i:j + 1])
                        i = j + 1
                        continue
            if text[i] == ";" and not in_dollar_quote:
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
            else:
                current.append(text[i])
            i += 1
        stmt = "".join(current).strip()
        if stmt:
            statements.append(stmt)
        return statements

    def strip_comments(chunk: str) -> str:
        """Remove line and inline comments (-- ...) and return stripped SQL."""
        lines = []
        for line in chunk.splitlines():
            if "--" in line:
                line = line.split("--")[0].rstrip()
            stripped = line.strip()
            if stripped and not stripped.startswith("--"):
                lines.append(line)
        out = "\n".join(lines).strip()
        sql_starts = ("CREATE", "INSERT", "ALTER", "DROP", "SELECT", "WITH", "ON ")
        while out and not any(out.strip().upper().startswith(s) for s in sql_starts):
            first_line = out.split("\n")[0]
            out = out[len(first_line):].lstrip("\n").strip()
            if out == first_line:
                break
        return out

    statements = []
    for s in _split_sql(sql):
        stmt = strip_comments(s)
        if stmt:
            statements.append(stmt)

    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")
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
        for stmt in statements:
            if stmt:
                cur.execute(stmt)
                print("OK:", stmt[:60].replace("\n", " ") + "..." if len(stmt) > 60 else stmt)
        cur.close()
        conn.close()
        print("Migration completed.")
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
