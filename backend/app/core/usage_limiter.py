"""Per-user Gemini usage caps (Phase 12, BYOK).

Each user pays with their own key, so these caps are not billing controls:
they are fat-finger / runaway-loop guards (a stuck client retrying chat
hundreds of times). Defaults: 30 Gemini calls/hour, 100/day per user,
configurable via ``GEMINI_CALLS_PER_USER_PER_HOUR`` /
``GEMINI_CALLS_PER_USER_PER_DAY``.

Honest limit: in file mode the counters are in-memory (reset on restart);
in Postgres mode they are durable rows in ``jarvis_usage`` and survive
restarts. On Vercel with several warm instances, file-mode counters are
per-instance — Postgres mode is the accurate one.

The limiter is kind-aware: ``kind="gemini"`` caps Gemini calls, while
``kind="search"`` caps web searches (which spend the owner's shared
``SEARCH_API_KEY``) under ``SEARCH_CALLS_PER_USER_PER_HOUR`` /
``SEARCH_CALLS_PER_USER_PER_DAY``. ``check`` and ``record`` are separate
so callers can check before a call and only consume quota when the call
actually succeeded.
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.store import get_user_store
from app.core.user_context import UserIdentity, resolve_user


class UsageLimiter:
    def __init__(self):
        pass

    def _caps_for(self, kind: str) -> Tuple[int, int]:
        """(per-hour, per-day) caps for a usage kind."""
        if kind == "search":
            return (
                settings.SEARCH_CALLS_PER_USER_PER_HOUR,
                settings.SEARCH_CALLS_PER_USER_PER_DAY,
            )
        return (
            settings.GEMINI_CALLS_PER_USER_PER_HOUR,
            settings.GEMINI_CALLS_PER_USER_PER_DAY,
        )

    def _label(self, kind: str) -> str:
        return "search" if kind == "search" else "Gemini"

    def check(self, user: Optional[UserIdentity] = None, kind: str = "gemini") -> None:
        """Raise 429 if the user is over either cap for this kind."""
        u = resolve_user(user)
        store = get_user_store()
        now = time.time()
        per_hour, per_day = self._caps_for(kind)
        label = self._label(kind)
        hour_count = store.count_usage_since(u, kind, now - 3600)
        if hour_count >= per_hour:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"{label} limit reached ({per_hour} {label} calls per hour). "
                    "Wait a little before trying again."
                    if kind == "search"
                    else f"Hourly limit reached ({per_hour} Gemini "
                    "calls per hour). Wait a little, or raise the limit in settings — "
                    "your own key pays for the calls."
                ),
                headers={"Retry-After": "3600"},
            )
        day_count = store.count_usage_since(u, kind, now - 86400)
        if day_count >= per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"{label} limit reached ({per_day} {label} calls per day). "
                    "It resets tomorrow."
                    if kind == "search"
                    else f"Daily limit reached ({per_day} Gemini "
                    "calls per day). It resets tomorrow."
                ),
                headers={"Retry-After": "86400"},
            )

    def record(self, user: Optional[UserIdentity] = None, kind: str = "gemini") -> None:
        """Record one (successful) call for this user/kind."""
        get_user_store().record_usage(resolve_user(user), kind)

    def check_and_record(self, user: Optional[UserIdentity] = None, kind: str = "gemini") -> None:
        """Raise 429 if the user is over either cap, else record one call."""
        self.check(user, kind=kind)
        self.record(user, kind=kind)

    def reset(self) -> None:
        """Test helper: clear in-memory file-mode counters."""
        store = get_user_store()
        if hasattr(store, "_usage"):
            store._usage.clear()  # type: ignore[attr-defined]


usage_limiter = UsageLimiter()
