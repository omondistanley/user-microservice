"""
Sprint 4 — Gmail OAuth2 + Pub/Sub receipt ingestion.

Flow:
  1. User authorises Gmail read-only access via OAuth2 (PKCE not required for
     server-side flow; we use authorization_code grant).
  2. We call gmail.users.watch() with a Pub/Sub topic so Google pushes new-mail
     notifications to our /gmail/webhook endpoint instead of us polling.
  3. On each Pub/Sub push we fetch new messages since the stored historyId,
     parse merchant + amount from the email subject/body, classify the
     transaction, and create an expense.
  4. Tokens are stored encrypted (Fernet) in gmail_oauth_token; processing
     history in gmail_receipt_processed prevents double-creates.

Config env vars required:
  GMAIL_CLIENT_ID          — Google OAuth client_id
  GMAIL_CLIENT_SECRET      — Google OAuth client_secret
  GMAIL_REDIRECT_URI       — OAuth redirect URI (e.g. https://app.pocketii.app/api/v1/gmail/oauth/callback)
  GMAIL_PUBSUB_TOPIC       — projects/<project>/topics/<topic>
  ENCRYPTION_KEY           — Fernet key (already used by Plaid token storage)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("gmail_receipt_service")

SCHEMA = "expenses_db"
TOKEN_TABLE = "gmail_oauth_token"
PROCESSED_TABLE = "gmail_receipt_processed"

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _gmail_client_id() -> str:
    return os.environ.get("GMAIL_CLIENT_ID", "")

def _gmail_client_secret() -> str:
    return os.environ.get("GMAIL_CLIENT_SECRET", "")

def _gmail_redirect_uri() -> str:
    return os.environ.get("GMAIL_REDIRECT_URI", "")

def _pubsub_topic() -> str:
    return os.environ.get("GMAIL_PUBSUB_TOPIC", "")

def _encryption_key() -> Optional[str]:
    return os.environ.get("ENCRYPTION_KEY", "") or None

def is_configured() -> bool:
    return bool(_gmail_client_id() and _gmail_client_secret() and _gmail_redirect_uri())

# ---------------------------------------------------------------------------
# Fernet token encryption (same key as Plaid access token)
# ---------------------------------------------------------------------------

def _encrypt(plaintext: str) -> str:
    """Fernet-encrypt a string; returns base64url ciphertext."""
    key = _encryption_key()
    if not key:
        # No encryption key: store as-is (dev/test only — log a warning)
        logger.warning("ENCRYPTION_KEY not set; storing Gmail token unencrypted")
        return plaintext
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key.encode() if isinstance(key, str) else key)
        return f.encrypt(plaintext.encode()).decode()
    except Exception as exc:
        logger.error("gmail_token_encrypt_failed: %s", exc)
        raise


def _decrypt(ciphertext: str) -> str:
    """Fernet-decrypt; returns plaintext. Handles unencrypted dev tokens."""
    key = _encryption_key()
    if not key:
        return ciphertext
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key.encode() if isinstance(key, str) else key)
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Fallback: might be an unencrypted legacy value
        return ciphertext

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_conn(context: Dict[str, Any]):
    conn = psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "expenses_db"),
        cursor_factory=RealDictCursor,
    )
    conn.autocommit = False
    return conn

# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def get_authorization_url(state: str) -> str:
    """Return the Google OAuth2 authorization URL to redirect the user to."""
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": _gmail_client_id(),
                    "client_secret": _gmail_client_secret(),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [_gmail_redirect_uri()],
                }
            },
            scopes=_GMAIL_SCOPES,
        )
        flow.redirect_uri = _gmail_redirect_uri()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url
    except ImportError:
        raise RuntimeError(
            "google-auth-oauthlib not installed. "
            "Add google-auth-oauthlib and google-api-python-client to requirements."
        )


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """
    Exchange an authorization code for OAuth2 tokens.
    Returns a dict with access_token, refresh_token, etc.
    """
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": _gmail_client_id(),
                    "client_secret": _gmail_client_secret(),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [_gmail_redirect_uri()],
                }
            },
            scopes=_GMAIL_SCOPES,
        )
        flow.redirect_uri = _gmail_redirect_uri()
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or _GMAIL_SCOPES),
        }
    except ImportError:
        raise RuntimeError("google-auth-oauthlib not installed.")


def fetch_gmail_profile_email(access_token: str) -> Optional[str]:
    """Resolve the mailbox address for the authorized Gmail user (for Pub/Sub routing)."""
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from googleapiclient.discovery import build  # type: ignore

        creds = Credentials(token=access_token)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        prof = service.users().getProfile(userId="me").execute()
        return (prof or {}).get("emailAddress")
    except Exception as exc:
        logger.warning("gmail_profile_email_failed: %s", exc)
        return None


def resolve_user_id_by_google_email(context: Dict[str, Any], email: str) -> Optional[int]:
    """Map Gmail push notification emailAddress to app user_id."""
    if not email or not str(email).strip():
        return None
    normalized = str(email).strip().lower()
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT user_id FROM {SCHEMA}.{TOKEN_TABLE}
                WHERE lower(google_account_email::text) = %s
                LIMIT 1
                """,
                (normalized,),
            )
            row = cur.fetchone()
        return int(row["user_id"]) if row else None
    finally:
        conn.close()


def decode_gmail_pubsub_data(encoded_data: str) -> Dict[str, Any]:
    try:
        raw = base64.b64decode(encoded_data + "==").decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception as exc:
        logger.warning("gmail_pubsub_decode_failed: %s", exc)
        return {}


def delete_gmail_oauth_for_user(context: Dict[str, Any], user_id: int) -> int:
    """Remove stored Gmail tokens (and processed-message log) for user. Returns rows deleted from token table."""
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {SCHEMA}.{PROCESSED_TABLE} WHERE user_id = %s", (user_id,))
            cur.execute(
                f"DELETE FROM {SCHEMA}.{TOKEN_TABLE} WHERE user_id = %s RETURNING user_id",
                (user_id,),
            )
            n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def save_oauth_token(
    context: Dict[str, Any],
    user_id: int,
    token_data: Dict[str, Any],
    google_account_email: Optional[str] = None,
) -> None:
    """Encrypt and upsert OAuth token for user_id. Preserves google_account_email on token refresh when email is omitted."""
    clean = {k: v for k, v in token_data.items() if not str(k).startswith("_")}
    encrypted = _encrypt(json.dumps(clean))
    email_val = (google_account_email or "").strip() or None
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {SCHEMA}.{TOKEN_TABLE} (user_id, encrypted_token, google_account_email, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    encrypted_token = EXCLUDED.encrypted_token,
                    google_account_email = COALESCE(
                        EXCLUDED.google_account_email,
                        {TOKEN_TABLE}.google_account_email
                    ),
                    updated_at = now()
                """,
                (user_id, encrypted, email_val),
            )
        conn.commit()
    finally:
        conn.close()


def load_oauth_token(context: Dict[str, Any], user_id: int) -> Optional[Dict[str, Any]]:
    """Return decrypted token dict for user_id, or None if not found."""
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT encrypted_token, history_id, watch_expiry, google_account_email
                    FROM {SCHEMA}.{TOKEN_TABLE} WHERE user_id = %s""",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        token_data = json.loads(_decrypt(row["encrypted_token"]))
        token_data["_history_id"] = row.get("history_id")
        token_data["_watch_expiry"] = row.get("watch_expiry")
        if row.get("google_account_email"):
            token_data["_google_account_email"] = row["google_account_email"]
        return token_data
    finally:
        conn.close()


def update_history_id(context: Dict[str, Any], user_id: int, history_id: int) -> None:
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {SCHEMA}.{TOKEN_TABLE} SET history_id = %s, updated_at = now() WHERE user_id = %s",
                (history_id, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_watch_metadata(
    context: Dict[str, Any], user_id: int, expiry: datetime, resource: str
) -> None:
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {SCHEMA}.{TOKEN_TABLE}
                    SET watch_expiry = %s, watch_resource = %s, updated_at = now()
                    WHERE user_id = %s""",
                (expiry, resource, user_id),
            )
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Pub/Sub watch registration
# ---------------------------------------------------------------------------

def register_gmail_watch(context: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """
    Call Gmail users.watch() to register a Pub/Sub push subscription.
    Requires GMAIL_PUBSUB_TOPIC to be set.
    Returns {historyId, expiration} from the API or raises.
    """
    token_data = load_oauth_token(context, user_id)
    if not token_data:
        raise ValueError(f"No Gmail OAuth token for user_id={user_id}")
    topic = _pubsub_topic()
    if not topic:
        raise ValueError("GMAIL_PUBSUB_TOPIC not configured")
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id", _gmail_client_id()),
            client_secret=token_data.get("client_secret", _gmail_client_secret()),
            scopes=token_data.get("scopes", _GMAIL_SCOPES),
        )
        service = build("gmail", "v1", credentials=creds)
        result = service.users().watch(
            userId="me",
            body={
                "topicName": topic,
                "labelIds": ["INBOX"],
                "labelFilterAction": "include",
            },
        ).execute()
        # Save updated access token if refreshed
        if creds.token and creds.token != token_data.get("access_token"):
            token_data["access_token"] = creds.token
            save_oauth_token(context, user_id, {k: v for k, v in token_data.items() if not k.startswith("_")})
        history_id = int(result.get("historyId", 0))
        expiry_ms = int(result.get("expiration", 0))
        expiry = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc) if expiry_ms else None
        if history_id:
            update_history_id(context, user_id, history_id)
        if expiry:
            update_watch_metadata(context, user_id, expiry, topic)
        logger.info("gmail_watch_registered user_id=%s historyId=%s", user_id, history_id)
        return result
    except ImportError:
        raise RuntimeError("google-api-python-client not installed.")

# ---------------------------------------------------------------------------
# Receipt email parsing
# ---------------------------------------------------------------------------

# Common patterns: "$12.34", "12.34 USD", "USD 12.34", "£12.34", "€12,34"
_AMOUNT_PATTERNS = [
    re.compile(r"(?:total|amount|charged|paid)[:\s]*[$£€¥]?\s*(\d[\d,]*\.?\d{0,2})", re.IGNORECASE),
    re.compile(r"[$£€¥]\s*(\d[\d,]*\.?\d{0,2})"),
    re.compile(r"(\d[\d,]*\.\d{2})\s*(?:USD|GBP|EUR|CAD|AUD)", re.IGNORECASE),
]

_MERCHANT_SUBJECTS = [
    re.compile(r"(?:receipt|order|purchase|confirmation)\s+(?:from|at|for)\s+(.+?)(?:\s+[-–—]|\s+#|\s+\d|$)", re.IGNORECASE),
    re.compile(r"your\s+(.+?)\s+(?:receipt|order|purchase)", re.IGNORECASE),
]


def _parse_amount(text: str) -> Optional[Decimal]:
    for pattern in _AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                val = Decimal(raw)
                if val > 0:
                    return val
            except InvalidOperation:
                continue
    return None


def _parse_merchant(subject: str, from_address: str) -> str:
    for pattern in _MERCHANT_SUBJECTS:
        m = pattern.search(subject)
        if m:
            merchant = m.group(1).strip()
            if 2 < len(merchant) < 100:
                return merchant
    # Fallback: extract display name from From header  e.g. "Uber Receipts <receipts@uber.com>"
    from_match = re.match(r"^(.+?)\s*<", from_address or "")
    if from_match:
        return from_match.group(1).strip()
    # Last resort: domain from email address
    email_match = re.search(r"@([\w.-]+)", from_address or "")
    if email_match:
        domain = email_match.group(1).split(".")[0]
        return domain.capitalize()
    return "Unknown merchant"


def parse_receipt_email(
    subject: str,
    body_text: str,
    from_address: str,
    received_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extract merchant, amount, and date from a receipt email.
    Returns None if no amount can be found.
    """
    combined = f"{subject}\n{body_text}"
    amount = _parse_amount(combined)
    if amount is None:
        return None
    merchant = _parse_merchant(subject, from_address)
    tx_date = received_date or datetime.now(timezone.utc).date().isoformat()
    return {
        "merchant": merchant,
        "amount": float(amount),
        "date": tx_date[:10],
        "source_email_subject": subject[:500],
        "from_address": from_address[:255],
    }

# ---------------------------------------------------------------------------
# Gmail message fetching
# ---------------------------------------------------------------------------

def _build_gmail_service(token_data: Dict[str, Any]):
    """Build an authenticated Gmail API service object."""
    from google.oauth2.credentials import Credentials  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id", _gmail_client_id()),
        client_secret=token_data.get("client_secret", _gmail_client_secret()),
        scopes=token_data.get("scopes", _GMAIL_SCOPES),
    )
    return build("gmail", "v1", credentials=creds), creds


def _get_message_text(service, message_id: str) -> Tuple[str, str, str, str]:
    """
    Fetch a Gmail message; return (subject, body_text, from_address, date_str).
    """
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in (msg.get("payload", {}).get("headers") or [])}
    subject = headers.get("subject", "")
    from_addr = headers.get("from", "")
    date_str = headers.get("date", "")
    # Parse received date to ISO
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        iso_date = dt.date().isoformat()
    except Exception:
        iso_date = datetime.now(timezone.utc).date().isoformat()

    # Extract plain text body
    body_text = ""
    payload = msg.get("payload", {})
    parts = payload.get("parts") or [payload]
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = (part.get("body") or {}).get("data", "")
            if data:
                try:
                    body_text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                    break
                except Exception:
                    pass

    return subject, body_text[:4000], from_addr, iso_date


def _is_receipt_email(subject: str, from_address: str) -> bool:
    """Quick filter: is this likely a receipt/purchase confirmation?"""
    receipt_keywords = [
        "receipt", "order confirmation", "purchase", "payment confirmation",
        "invoice", "transaction", "you paid", "your order", "charged",
    ]
    text = f"{subject} {from_address}".lower()
    return any(kw in text for kw in receipt_keywords)


def _mark_processed(
    context: Dict[str, Any],
    user_id: int,
    message_id: str,
    thread_id: str,
    subject: str,
    from_address: str,
    expense_id: Optional[str],
) -> bool:
    """
    Insert into gmail_receipt_processed for idempotency.
    Returns True if inserted (new), False if already processed (conflict).
    """
    conn = _get_conn(context)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {SCHEMA}.{PROCESSED_TABLE}
                    (user_id, message_id, thread_id, subject, from_address, expense_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, message_id) DO NOTHING
                RETURNING id
                """,
                (user_id, message_id, thread_id, subject[:500], from_address[:255],
                 expense_id),
            )
            inserted = cur.fetchone() is not None
        conn.commit()
        return inserted
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Main ingestion entry point
# ---------------------------------------------------------------------------

def process_pubsub_notification(
    context: Dict[str, Any],
    user_id: int,
    encoded_data: str,
) -> List[Dict[str, Any]]:
    """
    Handle a Pub/Sub push notification for a user.
    Decodes the push data, fetches new Gmail messages since last historyId,
    parses receipt emails, and creates expenses.

    Returns list of {message_id, status, expense_id?, reason?} for each message.
    """
    try:
        raw = base64.b64decode(encoded_data + "==").decode("utf-8", errors="replace")
        notification = json.loads(raw)
    except Exception as exc:
        logger.warning("gmail_pubsub_decode_failed: %s", exc)
        return []

    new_history_id = int(notification.get("historyId", 0))
    if not new_history_id:
        return []

    token_data = load_oauth_token(context, user_id)
    if not token_data:
        logger.warning("gmail_no_token user_id=%s", user_id)
        return []

    last_history_id = token_data.get("_history_id") or 0

    results: List[Dict[str, Any]] = []
    try:
        from googleapiclient.discovery import build  # type: ignore
        service, creds = _build_gmail_service(token_data)

        # Fetch message IDs added since last_history_id
        if last_history_id:
            history_resp = service.users().history().list(
                userId="me",
                startHistoryId=str(last_history_id),
                historyTypes=["messageAdded"],
                labelId="INBOX",
            ).execute()
            histories = history_resp.get("history", [])
            message_ids = []
            for h in histories:
                for ma in h.get("messagesAdded", []):
                    mid = ma.get("message", {}).get("id")
                    if mid:
                        message_ids.append(mid)
        else:
            # First sync: fetch last 10 inbox messages
            list_resp = service.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=10
            ).execute()
            message_ids = [m["id"] for m in (list_resp.get("messages") or [])]

        # Save updated access token if credentials were refreshed
        if creds.token and creds.token != token_data.get("access_token"):
            token_data["access_token"] = creds.token
            save_oauth_token(
                context,
                user_id,
                {k: v for k, v in token_data.items() if not k.startswith("_")},
                google_account_email=token_data.get("_google_account_email"),
            )

        for message_id in message_ids:
            try:
                subject, body_text, from_addr, iso_date = _get_message_text(service, message_id)
                thread_id = ""

                if not _is_receipt_email(subject, from_addr):
                    results.append({"message_id": message_id, "status": "skipped", "reason": "not_receipt"})
                    continue

                parsed = parse_receipt_email(subject, body_text, from_addr, iso_date)
                if parsed is None:
                    results.append({"message_id": message_id, "status": "skipped", "reason": "no_amount_found"})
                    continue

                # Import here to avoid circular dependencies
                from app.services.transaction_classifier import classify_transaction
                from app.services.expense_data_service import ExpenseDataService
                from app.resources.expense_resource import ExpenseResource
                from app.models.expenses import ExpenseCreate

                eds = ExpenseDataService(context)
                resource = ExpenseResource(eds)
                classification = classify_transaction(
                    amount=Decimal(str(parsed["amount"])),
                    merchant=parsed["merchant"],
                    note=parsed.get("source_email_subject"),
                )
                try:
                    from datetime import date as date_type
                    tx_date = date_type.fromisoformat(parsed["date"])
                except Exception:
                    tx_date = datetime.now(timezone.utc).date()

                payload = ExpenseCreate(
                    amount=Decimal(str(parsed["amount"])),
                    date=tx_date,
                    category_code=classification.category_code or 8,
                    currency="USD",
                    description=(
                        f"{parsed['merchant']} | {parsed.get('source_email_subject', '')}"
                    )[:2000],
                )
                created = resource.create(
                    user_id,
                    payload,
                    source="gmail_receipt",
                )
                expense_id_str = str(created.expense_id)

                inserted = _mark_processed(
                    context, user_id, message_id, thread_id, subject, from_addr, expense_id_str
                )
                if not inserted:
                    results.append({"message_id": message_id, "status": "duplicate", "expense_id": expense_id_str})
                else:
                    results.append({"message_id": message_id, "status": "created", "expense_id": expense_id_str})

            except Exception as exc:
                logger.warning("gmail_message_process_failed mid=%s: %s", message_id, exc)
                results.append({"message_id": message_id, "status": "error", "reason": str(exc)})

    except ImportError:
        raise RuntimeError("google-api-python-client not installed.")
    except Exception as exc:
        logger.error("gmail_history_fetch_failed user_id=%s: %s", user_id, exc)
        return results
    finally:
        # Always advance the historyId cursor
        if new_history_id:
            update_history_id(context, user_id, new_history_id)

    return results
