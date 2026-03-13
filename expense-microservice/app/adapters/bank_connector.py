"""
Phase 7: Bank connector abstraction. Implementations: Plaid, Teller.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BankConnectorAdapter(ABC):
    """Provider interface for bank linking and transaction sync."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """e.g. 'plaid', 'teller'."""
        pass

    @abstractmethod
    def create_link_session(self, user_id: int) -> Optional[str]:
        """Return link token / session URL for initializing the connection flow."""
        pass

    @abstractmethod
    def exchange_public_token(self, user_id: int, public_token: str) -> Optional[Dict[str, Any]]:
        """Exchange public token for access; store item and return item summary."""
        pass

    @abstractmethod
    def sync_transactions(
        self,
        user_id: int,
        item_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync transactions for the linked item; return counts/summary."""
        pass

    @abstractmethod
    def disconnect_item(self, user_id: int, item_id: str) -> bool:
        """Revoke access and remove stored credentials."""
        pass

    def list_items(self, user_id: int) -> List[Dict[str, Any]]:
        """List linked items for the user. Override if provider-specific."""
        return []
