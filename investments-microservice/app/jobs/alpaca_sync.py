"""
Sync Alpaca positions into holdings for all connected users.
Run periodically (scheduler) or on-demand. For each user with an alpaca_connection,
fetches positions from Alpaca Trading API, replaces holdings with source='alpaca', then marks sync.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.alpaca_broker_client import get_positions, position_to_holding_row
from app.services.alpaca_connection_service import AlpacaConnectionService
from app.services.holdings_data_service import HoldingsDataService

logger = logging.getLogger(__name__)

DB_CONTEXT = {
    "host": DB_HOST or "localhost",
    "port": int(DB_PORT) if DB_PORT else 5432,
    "user": DB_USER or "postgres",
    "password": DB_PASSWORD or "postgres",
    "dbname": DB_NAME or "investments_db",
}


def run_alpaca_sync(job_id: str = "") -> dict:
    """
    For each user with an Alpaca connection: fetch positions, replace alpaca holdings, mark sync.
    Returns { "processed": int, "errors": list }.
    """
    conn_svc = AlpacaConnectionService(context=DB_CONTEXT)
    holdings_svc = HoldingsDataService(context=DB_CONTEXT)
    user_ids = conn_svc.list_connection_user_ids()
    processed = 0
    errors = []
    for user_id in user_ids:
        try:
            creds = conn_svc.get_credentials(user_id)
            if not creds:
                errors.append({"user_id": user_id, "error": "no_credentials"})
                continue
            positions = get_positions(
                api_key_id=creds["api_key_id"],
                api_key_secret=creds["api_key_secret"],
                is_paper=creds["is_paper"],
            )
            # Replace all alpaca holdings: delete then insert
            deleted = holdings_svc.delete_holdings_by_source(user_id, "alpaca")
            if deleted:
                logger.info("alpaca_sync user_id=%s deleted %d alpaca holdings", user_id, deleted)
            now = datetime.now(timezone.utc)
            for i, pos in enumerate(positions):
                external_id = pos.get("asset_id") or pos.get("symbol") or f"pos_{i}"
                row = position_to_holding_row(user_id, pos, str(external_id))
                if not row:
                    continue
                row["created_at"] = now
                row["updated_at"] = now
                try:
                    holdings_svc.insert_holding(row)
                except Exception as e:
                    logger.warning("alpaca_sync insert_holding user_id=%s symbol=%s error=%s", user_id, row.get("symbol"), e)
                    errors.append({"user_id": user_id, "symbol": row.get("symbol"), "error": str(e)})
            conn_svc.mark_sync(user_id, when=now)
            processed += 1
        except Exception as e:
            logger.exception("alpaca_sync user_id=%s error=%s", user_id, e)
            errors.append({"user_id": user_id, "error": str(e)})
    return {"processed": processed, "errors": errors, "job_id": job_id}


def run_alpaca_sync_for_user(user_id: int) -> dict:
    """
    Sync Alpaca positions for a single user. Used by the user-triggered /alpaca/sync endpoint.
    Returns { "synced": int, "errors": list } or { "error": str } if not connected.
    """
    conn_svc = AlpacaConnectionService(context=DB_CONTEXT)
    holdings_svc = HoldingsDataService(context=DB_CONTEXT)
    creds = conn_svc.get_credentials(user_id)
    if not creds:
        return {"error": "Alpaca not connected. Link your account first."}
    errors = []
    try:
        positions = get_positions(
            api_key_id=creds["api_key_id"],
            api_key_secret=creds["api_key_secret"],
            is_paper=creds["is_paper"],
        )
        holdings_svc.delete_holdings_by_source(user_id, "alpaca")
        now = datetime.now(timezone.utc)
        synced = 0
        for i, pos in enumerate(positions):
            external_id = pos.get("asset_id") or pos.get("symbol") or f"pos_{i}"
            row = position_to_holding_row(user_id, pos, str(external_id))
            if not row:
                continue
            row["created_at"] = now
            row["updated_at"] = now
            try:
                holdings_svc.insert_holding(row)
                synced += 1
            except Exception as e:
                logger.warning("alpaca_sync_for_user insert user_id=%s symbol=%s error=%s", user_id, row.get("symbol"), e)
                errors.append({"symbol": row.get("symbol"), "error": str(e)})
        conn_svc.mark_sync(user_id, when=now)
        return {"synced": synced, "errors": errors}
    except Exception as e:
        logger.exception("alpaca_sync_for_user user_id=%s error=%s", user_id, e)
        return {"error": str(e)}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_alpaca_sync(job_id="cli")
    print(result)
    sys.exit(0 if not result.get("errors") else 1)
