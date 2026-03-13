"""
Phase 7: Digest sender job. Sends weekly/monthly email digest for users with active config.
Usage: python -m app.jobs.digest_sender --as-of YYYY-MM-DD [--dry-run] [--frequency weekly|monthly]
"""
import argparse
import sys
from datetime import date

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    EMAIL_MODE,
    SMTP_FROM,
)

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


def _get_digest_configs(frequency: str):
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT id, user_id, channel, channel_target FROM "{SCHEMA}".digest_config '
            "WHERE is_active = TRUE AND frequency = %s",
            (frequency,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _send_email(to: str, subject: str, body: str) -> bool:
    if EMAIL_MODE != "smtp" or not to:
        print("[console] Digest to %s: %s" % (to or "(none)", subject))
        return True
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM or "noreply@localhost"
        msg["To"] = to
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_HOST or "localhost", SMTP_PORT or 587) as s:
            if SMTP_USER and SMTP_PASSWORD:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception as e:
        print("Send failed: %s" % e, file=sys.stderr)
        return False


def _mark_sent(config_id: int):
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'UPDATE "{SCHEMA}".digest_config SET last_sent_at = now(), updated_at = now() WHERE id = %s',
            (config_id,),
        )
    finally:
        conn.close()


def run(as_of: date, dry_run: bool, frequency: str):
    configs = _get_digest_configs(frequency)
    sent = 0
    for c in configs:
        to = c.get("channel_target") if c.get("channel") == "email" else None
        if not to and c.get("channel") == "email":
            conn = _get_connection()
            cur = conn.cursor()
            cur.execute('SELECT email FROM users_db."user" WHERE id = %s', (c["user_id"],))
            row = cur.fetchone()
            to = row["email"] if row else None
            conn.close()
        subject = "Expense Tracker %s digest" % frequency.capitalize()
        body = "Your %s digest for %s. View your dashboard for details." % (frequency, as_of.isoformat())
        if dry_run:
            print("Would send to user_id=%s to=%s" % (c["user_id"], to))
            sent += 1
            continue
        if _send_email(to or "", subject, body):
            _mark_sent(c["id"])
            sent += 1
    return sent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True, help="Reference date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--frequency", default="weekly", choices=["weekly", "monthly"])
    args = parser.parse_args()
    try:
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        print("Invalid --as-of", file=sys.stderr)
        sys.exit(1)
    n = run(as_of, args.dry_run, args.frequency)
    print("Digest sent: %s" % n)


if __name__ == "__main__":
    main()
