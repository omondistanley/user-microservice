"""Phase 7: Plaid implementation of BankConnectorAdapter."""
from typing import Any, Dict, List, Optional

from app.adapters.bank_connector import BankConnectorAdapter
from app.services.plaid_data_service import PlaidDataService
from app.services.plaid_service import (
    create_link_token,
    exchange_public_token as plaid_exchange,
    fetch_transactions,
    is_configured,
    item_get,
    encrypt_access_token,
)


class PlaidAdapter(BankConnectorAdapter):
    def __init__(self, plaid_data_service: PlaidDataService):
        self._data = plaid_data_service

    @property
    def provider_name(self) -> str:
        return "plaid"

    def create_link_session(self, user_id: int) -> Optional[str]:
        if not is_configured():
            return None
        return create_link_token(user_id)

    def exchange_public_token(self, user_id: int, public_token: str) -> Optional[Dict[str, Any]]:
        if not is_configured():
            return None
        result = plaid_exchange(public_token)
        if not result:
            return None
        access_token = result.get("access_token")
        item_id = result.get("item_id")
        if not access_token or not item_id:
            return None
        encrypted = encrypt_access_token(access_token)
        if not encrypted:
            return None
        item_info = item_get(access_token)
        institution_id = item_info.get("institution_id") if item_info else None
        institution_name = (item_info.get("institution_name") or "Linked account") if item_info else "Linked account"
        return self._data.save_plaid_item(
            user_id=user_id,
            item_id=item_id,
            access_token_encrypted=encrypted,
            institution_id=institution_id,
            institution_name=institution_name,
        )

    def sync_transactions(
        self,
        user_id: int,
        item_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Delegate to existing Plaid sync flow (router calls fetch_transactions + expense create)
        count = 0
        try:
            txns = fetch_transactions(user_id, item_id, date_from=date_from, date_to=date_to)
            count = len(txns) if isinstance(txns, list) else 0
        except Exception:
            pass
        return {"synced": count, "provider": self.provider_name}

    def disconnect_item(self, user_id: int, item_id: str) -> bool:
        return self._data.delete_plaid_item(user_id, item_id)

    def list_items(self, user_id: int) -> List[Dict[str, Any]]:
        items = self._data.get_plaid_items(user_id)
        for it in items:
            it.setdefault("provider", self.provider_name)
        return items
