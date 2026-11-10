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
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.store import get_user_store
from app.core.user_context import UserIdentity, resolve_user


class UsageLimiter:
    def __init__(self):
        pass

    def check_and_record(self, user: Optional[UserIdentity] = None, kind: str = "gemini") -> None:
        """Raise 429 if the user is over either cap, else record one call."""
        u = resolve_user(user)
        store = get_user_store()
        now = time.time()
        hour_count = store.count_usage_since(u, kind, now - 3600)
        if hour_count >= settings.GEMINI_CALLS_PER_USER_PER_HOUR:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Hourly limit reached ({settings.GEMINI_CALLS_PER_USER_PER_HOUR} Gemini "
                    "calls per hour). Wait a little, or raise the limit in settings — "
                    "your own key pays for the calls."
                ),
                headers={"Retry-After": "3600"},
            )
        day_count = store.count_usage_since(u, kind, now - 86400)
        if day_count >= settings.GEMINI_CALLS_PER_USER_PER_DAY:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Daily limit reached ({settings.GEMINI_CALLS_PER_USER_PER_DAY} Gemini "
                    "calls per day). It resets tomorrow."
                ),
                headers={"Retry-After": "86400"},
            )
        store.record_usage(u, kind)

    def reset(self) -> None:
        """Test helper: clear in-memory file-mode counters."""
        store = get_user_store()
        if hasattr(store, "_usage"):
            store._usage.clear()  # type: ignore[attr-defined]


usage_limiter = UsageLimiter()
