"""
In-memory Remote Pairing and Session Management (Phase 11: Tailscale Phone-to-Laptop Control).

Security properties:
- Short-lived, one-time pairing codes generated exclusively on local laptop.
- Exchanged for cryptographically secure, in-memory session tokens.
- Tokens are NEVER persisted to disk, localStorage, cookies, or logs.
- Dedicated rate limiting against pairing brute-force enumeration.
- Revocation, expiry, and disconnect controls.
"""

import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.logger import app_logger


@dataclass
class PairingCodeInfo:
    code: str
    created_at: float
    expires_at: float
    is_used: bool = False


@dataclass
class RemoteSessionInfo:
    token: str
    created_at: float
    expires_at: float
    client_ip: str
    is_revoked: bool = False
    scopes: List[str] = field(default_factory=lambda: ["remote_control"])


class RemoteSessionManager:
    """
    Manages in-memory pairing codes and remote session tokens.
    All data is kept in volatile memory and purged on restart or expiry.
    """

    def __init__(self):
        self._pairing_codes: Dict[str, PairingCodeInfo] = {}
        self._sessions: Dict[str, RemoteSessionInfo] = {}
        self._pairing_failures: Dict[str, List[float]] = defaultdict(list)

    def _clean_rate_limit(self, ip: str, now: float) -> None:
        window = settings.PAIRING_RATE_LIMIT_WINDOW_SECONDS
        self._pairing_failures[ip] = [
            t for t in self._pairing_failures[ip] if now - t < window
        ]
        if not self._pairing_failures[ip]:
            self._pairing_failures.pop(ip, None)

    def _record_failure(self, ip: str) -> None:
        now = time.time()
        self._clean_rate_limit(ip, now)
        self._pairing_failures[ip].append(now)

    def is_pairing_rate_limited(self, ip: str) -> Tuple[bool, int]:
        now = time.time()
        self._clean_rate_limit(ip, now)
        failures = self._pairing_failures.get(ip, [])
        if len(failures) >= settings.PAIRING_RATE_LIMIT:
            oldest = failures[0]
            retry_after = max(1, int(settings.PAIRING_RATE_LIMIT_WINDOW_SECONDS - (now - oldest)))
            return True, retry_after
        return False, 0

    def generate_pairing_code(self) -> str:
        """
        Generate a 6-digit cryptographically secure pairing code.
        Invalidates any previous active codes to ensure single-code discipline.
        """
        now = time.time()
        # Invalidate previous unused codes
        for code_info in self._pairing_codes.values():
            if not code_info.is_used:
                code_info.is_used = True

        # Generate 6-digit number (100000 - 999999)
        code = str(secrets.randbelow(900000) + 100000)
        expires_at = now + settings.REMOTE_PAIRING_CODE_TIMEOUT_SECONDS

        self._pairing_codes[code] = PairingCodeInfo(
            code=code,
            created_at=now,
            expires_at=expires_at,
            is_used=False,
        )

        app_logger.info(
            "Generated one-time remote pairing code (valid for %ds). Displayed locally on laptop.",
            settings.REMOTE_PAIRING_CODE_TIMEOUT_SECONDS,
        )
        return code

    def exchange_pairing_code(self, code: str, client_ip: str) -> RemoteSessionInfo:
        """
        Exchange a one-time pairing code for an in-memory session token.
        Enforces rate limiting, single-use, and expiration.
        """
        now = time.time()
        # 1. Check rate limits
        is_limited, retry_after = self.is_pairing_rate_limited(client_ip)
        if is_limited:
            app_logger.warning("Pairing rate limit exceeded from %s. Retry after %ds.", client_ip, retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed pairing attempts. Please wait {retry_after} seconds before retrying.",
                headers={"Retry-After": str(retry_after)},
            )

        # 2. Check code presence and validity
        cleaned_code = code.strip()
        info = self._pairing_codes.get(cleaned_code)

        if not info:
            self._record_failure(client_ip)
            app_logger.warning("Invalid pairing code attempt from %s.", client_ip)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pairing code. Please generate a fresh code on your laptop.",
            )

        if info.is_used:
            self._record_failure(client_ip)
            app_logger.warning("Attempted reuse of pairing code from %s.", client_ip)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pairing code has already been used. Please generate a new code.",
            )

        if now > info.expires_at:
            self._record_failure(client_ip)
            app_logger.warning("Expired pairing code used from %s.", client_ip)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pairing code has expired. Please generate a new code on your laptop.",
            )

        # 3. Mark code used immediately
        info.is_used = True

        # 4. Generate in-memory session token (32 bytes urlsafe)
        token = secrets.token_urlsafe(32)
        session_expires_at = now + settings.REMOTE_SESSION_TIMEOUT_SECONDS

        session = RemoteSessionInfo(
            token=token,
            created_at=now,
            expires_at=session_expires_at,
            client_ip=client_ip,
            is_revoked=False,
            scopes=["remote_control"],
        )
        self._sessions[token] = session

        app_logger.info("Successfully paired remote client from %s. Session active for %ds.", client_ip, settings.REMOTE_SESSION_TIMEOUT_SECONDS)
        return session

    def validate_session_token(self, token: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Validate whether a session token is active, not expired, and not revoked.
        Returns (is_valid, failure_reason).
        """
        if not token:
            return False, "Missing session token."

        session = self._sessions.get(token.strip())
        if not session:
            return False, "Invalid session token."

        if session.is_revoked:
            return False, "Session token has been revoked."

        if time.time() > session.expires_at:
            return False, "Session token has expired."

        return True, None

    def get_session(self, token: Optional[str]) -> Optional[RemoteSessionInfo]:
        if not token:
            return None
        return self._sessions.get(token.strip())

    def revoke_session(self, token: str) -> bool:
        """Revoke a specific session token."""
        session = self._sessions.get(token.strip())
        if session:
            session.is_revoked = True
            app_logger.info("Revoked remote session token for client %s.", session.client_ip)
            return True
        return False

    def revoke_all_sessions(self) -> int:
        """Revoke all active remote sessions."""
        count = 0
        for s in self._sessions.values():
            if not s.is_revoked:
                s.is_revoked = True
                count += 1
        app_logger.info("Revoked all (%d) active remote sessions.", count)
        return count

    def get_active_sessions_count(self) -> int:
        now = time.time()
        return sum(
            1 for s in self._sessions.values()
            if not s.is_revoked and now <= s.expires_at
        )


remote_session_manager = RemoteSessionManager()
