"""
Send email via SMTP or log to console (EMAIL_MODE=console for dev).
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import (
    EMAIL_MODE,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
)


def send_email(to: str, subject: str, body_plain: str, body_html: str | None = None) -> None:
    """Send email to one recipient. In console mode, print to stdout."""
    if EMAIL_MODE == "console":
        print(f"[EMAIL] To: {to}")
        print(f"[EMAIL] Subject: {subject}")
        print(f"[EMAIL] Body:\n{body_plain}")
        if body_html:
            print("[EMAIL] (HTML body omitted from log)")
        return
    if EMAIL_MODE != "smtp" or not SMTP_HOST:
        print(f"[EMAIL] Mode={EMAIL_MODE}, not sending. To: {to}, Subject: {subject}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER or "noreply@localhost"
    msg["To"] = to
    msg.attach(MIMEText(body_plain, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_USER and SMTP_PASSWORD:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(msg["From"], [to], msg.as_string())
