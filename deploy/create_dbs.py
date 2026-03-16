#!/usr/bin/env python3
"""
Create users_db, expenses_db, budgets_db, investments_db if they do not exist.
Uses DB_HOST, DB_PORT, DB_USER, DB_PASSWORD from environment; connects to default 'postgres' DB.
Run during Fly release_command so migrations can run afterward.
"""
import os
import sys

try:
    import psycopg2
except ImportError:
    print("create_dbs: psycopg2 not found", file=sys.stderr)
    sys.exit(1)

DATABASES = ["users_db", "expenses_db", "budgets_db", "investments_db"]


def main():
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    # Connect to default maintenance database
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname="postgres",
            connect_timeout=10,
        )
        conn.autocommit = True
    except Exception as e:
        print(f"create_dbs: failed to connect to postgres at {host}:{port}: {e}", file=sys.stderr)
        sys.exit(1)

    cur = conn.cursor()
    for db in DATABASES:
        try:
            cur.execute(f'CREATE DATABASE "{db}"')
            print(f"create_dbs: created database {db}")
        except psycopg2.Error as e:
            if e.pgcode == "42P04":  # duplicate_database
                print(f"create_dbs: database {db} already exists, skipping")
            else:
                raise
        except Exception as e:
            print(f"create_dbs: error creating {db}: {e}", file=sys.stderr)
            cur.close()
            conn.close()
            sys.exit(1)
    cur.close()
    conn.close()
    print("create_dbs: done")


if __name__ == "__main__":
    main()
