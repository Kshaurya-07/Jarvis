import secrets
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings


class PendingAction(BaseModel):
    """Represents a state-changing action that requires explicit user confirmation."""
    confirmation_id: str
    tool_name: str
    arguments: Dict[str, Any]
    description: str
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    confirmed: bool = False
    # Google `sub` namespace of the user who requested it (None = legacy/local).
    # A confirmation can only be approved by the user who created it.
    user_sub: Optional[str] = None


class ConfirmationManager:
    """Manages pending confirmations for state-changing tools (e.g. app opening, screenshots)."""

    def __init__(self, timeout_seconds: Optional[int] = None):
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.CONFIRMATION_TIMEOUT_SECONDS
        )
        self._pending: Dict[str, PendingAction] = {}

    def create_pending_action(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        description: str,
        user: Optional[Any] = None,
    ) -> PendingAction:
        """Create and store a pending action requiring confirmation."""
        self.cleanup_expired()

        # Safe arguments copy (remove any confirmation_id from comparison)
        safe_args = {k: v for k, v in arguments.items() if k != "confirmation_id"}

        conf_id = f"conf_{secrets.token_hex(16)}"
        action = PendingAction(
            confirmation_id=conf_id,
            tool_name=tool_name,
            arguments=safe_args,
            description=description,
            created_at=time.time(),
            expires_at=time.time() + self._timeout_seconds,
            confirmed=False,
            user_sub=(user.sub if user is not None else None),
        )
        self._pending[conf_id] = action
        return action

    def get_action(self, confirmation_id: str) -> Optional[PendingAction]:
        """Retrieve a pending action by its ID if not expired."""
        self.cleanup_expired()
        return self._pending.get(confirmation_id)

    def confirm_action(self, confirmation_id: str, user: Optional[Any] = None) -> Optional[PendingAction]:
        """Explicitly confirm a pending action (only its owner may confirm)."""
        action = self.get_action(confirmation_id)
        if action:
            if user is not None and action.user_sub is not None and action.user_sub != user.sub:
                return None
            action.confirmed = True
            return action
        return None

    def validate_and_consume(
        self,
        confirmation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        user: Optional[Any] = None,
    ) -> bool:
        """
        Validates that a valid, unexpired, confirmed token exists and matches
        the tool and arguments exactly. Consumes the token upon verification (one-time use).
        """
        self.cleanup_expired()

        action = self._pending.get(confirmation_id)
        if not action:
            return False

        # Owner check: a confirmation belongs to the user who created it.
        if user is not None and action.user_sub is not None and action.user_sub != user.sub:
            return False

        # Verify tool name matches
        if action.tool_name != tool_name:
            return False

        # Verify arguments match (excluding confirmation_id)
        candidate_args = {k: v for k, v in arguments.items() if k != "confirmation_id"}
        if action.arguments != candidate_args:
            return False

        # Must be confirmed
        if not action.confirmed:
            return False

        # One-time use: consume and remove
        del self._pending[confirmation_id]
        return True

    def deny_action(self, confirmation_id: str, user: Optional[Any] = None) -> bool:
        """Deny and cancel a pending action (only its owner may deny)."""
        self.cleanup_expired()
        action = self._pending.get(confirmation_id)
        if action is not None and user is not None and action.user_sub is not None and action.user_sub != user.sub:
            return False
        if confirmation_id in self._pending:
            del self._pending[confirmation_id]
            return True
        return False

    def list_pending(self, user: Optional[Any] = None) -> List[PendingAction]:
        """List currently active pending actions (only the caller's own).

        Legacy entries (``user_sub=None``) belong to the local owner only:
        any other signed-in user never sees them.
        """
        self.cleanup_expired()
        items = [act for act in self._pending.values() if not act.confirmed]
        if user is not None:
            from app.core.user_context import resolve_user

            if resolve_user(user).is_local_owner:
                items = [a for a in items if a.user_sub is None or a.user_sub == user.sub]
            else:
                items = [a for a in items if a.user_sub == user.sub]
        return items

    def cleanup_expired(self) -> None:
        """Remove expired confirmations."""
        now = time.time()
        expired_ids = [k for k, v in self._pending.items() if v.expires_at < now]
        for k in expired_ids:
            del self._pending[k]


# Global instance
confirmation_manager = ConfirmationManager()
