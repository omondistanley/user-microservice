"""Gateway JWT path rules (no HTTP — logic only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import _requires_jwt


def test_validate_email_public():
    assert _requires_jwt("/api/v1/validate-email", "GET") is False


def test_apple_wallet_prefix_public():
    assert _requires_jwt("/api/v1/apple-wallet/webhook", "POST") is False


def test_plaid_webhook_public():
    assert _requires_jwt("/api/v1/plaid/webhook", "POST") is False


def test_gmail_webhook_post_public():
    assert _requires_jwt("/api/v1/gmail/webhook", "POST") is False


def test_gmail_status_requires_auth():
    assert _requires_jwt("/api/v1/gmail/status", "GET") is True


def test_expenses_requires_auth():
    assert _requires_jwt("/api/v1/expenses", "GET") is True


def test_gmail_webhook_get_requires_auth():
    assert _requires_jwt("/api/v1/gmail/webhook", "GET") is True
