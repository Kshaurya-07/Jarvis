import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, Request, status

from app.core.config import settings


class AuthFailureRateLimiter:
    """
    In-memory rate limiter tracking consecutive authentication and confirmation failures.
    Blocks callers exceeding failure threshold within a rolling window to defend
    against brute-force and credential enumeration attacks.
    """

    def __init__(self, max_failures: Optional[int] = None, window_seconds: Optional[int] = None):
        self._max_failures = max_failures if max_failures is not None else settings.AUTH_FAILURE_RATE_LIMIT
        self._window_seconds = window_seconds if window_seconds is not None else settings.AUTH_FAILURE_WINDOW_SECONDS
        self._failures: Dict[str, List[float]] = defaultdict(list)

    def _extract_ip(self, request: Request) -> str:
        """Extract client IP safely from request."""
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    def _clean_expired(self, ip: str, now: float) -> None:
        """Purge timestamps outside the rolling window."""
        self._failures[ip] = [t for t in self._failures[ip] if now - t < self._window_seconds]
        if not self._failures[ip]:
            self._failures.pop(ip, None)

    def record_failure(self, request_or_ip: Any) -> None:
        """Record an auth or confirmation failure for a client."""
        ip = request_or_ip if isinstance(request_or_ip, str) else self._extract_ip(request_or_ip)
        now = time.time()
        self._clean_expired(ip, now)
        self._failures[ip].append(now)

    def is_rate_limited(self, request_or_ip: Any) -> Tuple[bool, int]:
        """
        Check if client is currently rate-limited.
        Returns (is_limited, retry_after_seconds).
        """
        ip = request_or_ip if isinstance(request_or_ip, str) else self._extract_ip(request_or_ip)
        now = time.time()
        self._clean_expired(ip, now)

        history = self._failures.get(ip, [])
        if len(history) >= self._max_failures:
            oldest_relevant = history[0]
            retry_after = max(1, int(self._window_seconds - (now - oldest_relevant)))
            return True, retry_after
        return False, 0

    def check_request(self, request: Request) -> None:
        """
        Verifies that the client IP is not rate-limited.
        Raises HTTP 429 Too Many Requests with Retry-After header if blocked.
        """
        limited, retry_after = self.is_rate_limited(request)
        if limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many authentication or confirmation failures. Please retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self, ip: Optional[str] = None) -> None:
        """Reset failures for a specific IP or all IPs."""
        if ip:
            self._failures.pop(ip, None)
        else:
            self._failures.clear()


# Global instance
auth_rate_limiter = AuthFailureRateLimiter()
