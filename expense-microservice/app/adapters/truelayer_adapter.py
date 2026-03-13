"""TrueLayer (EU open banking) adapter skeleton. Implements BankConnectorAdapter; full OAuth/sync when credentials set."""
from typing import Any, Dict, List, Optional

from app.adapters.bank_connector import BankConnectorAdapter
from app.core.config import TRUELAYER_CLIENT_ID, TRUELAYER_CLIENT_SECRET


def is_configured() -> bool:
    return bool(TRUELAYER_CLIENT_ID and TRUELAYER_CLIENT_SECRET)


class TrueLayerAdapter(BankConnectorAdapter):
    """Skeleton for TrueLayer Data API. Returns None/empty when not configured or not implemented."""

    @property
    def provider_name(self) -> str:
        return "truelayer"

    def create_link_session(self, user_id: int) -> Optional[str]:
        if not is_configured():
            return None
        # TODO: build TrueLayer auth URL / link session when implementing full flow
        return None

    def exchange_public_token(self, user_id: int, public_token: str) -> Optional[Dict[str, Any]]:
        if not is_configured():
            return None
        # TODO: exchange code for access token, store item (e.g. in plaid_item with provider='truelayer')
        return None

    def sync_transactions(
        self,
        user_id: int,
        item_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {"synced": 0, "provider": self.provider_name}

    def disconnect_item(self, user_id: int, item_id: str) -> bool:
        return False

    def list_items(self, user_id: int) -> List[Dict[str, Any]]:
        return []
