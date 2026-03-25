#!/usr/bin/env python3
"""
Run migrations without psql. Uses same DB config as the app (env or defaults).
Usage: python run_migration.py [migration_file]
Default: migrations/create_user_table.sql
"""
import os
import sys
from pathlib import Path

# Load .env from user-microservice directory so DB_* are set when present
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

import psycopg2

# Same defaults as app
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "users_db")

def main():
    root = Path(__file__).resolve().parent
    migration = root / (sys.argv[1] if len(sys.argv) > 1 else "migrations/create_user_table.sql")
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

    # Run each statement. Strip leading full-line comments so
    # ";\n-- comment\nCREATE TABLE ..." is not skipped.
    statements = []
    for s in _split_sql(sql):
        s = s.strip()
        if not s:
            continue
        lines = s.split("\n")
        while lines and lines[0].strip().startswith("--"):
            lines.pop(0)
        stmt = "\n".join(lines).strip()
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
