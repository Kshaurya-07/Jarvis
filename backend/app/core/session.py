"""Stateless session tokens (Phase 12).

Jarvis sessions are HS256 JSON Web Tokens signed with ``SESSION_SECRET``
using only the standard library (no PyJWT dependency). Statelessness is
deliberate: on Vercel serverless there is no shared in-memory session
store, so the token itself must carry the identity. The same helpers sign
the short-lived OAuth-state cookie used by the Google login flow, so the
login flow also survives cold starts (no server-side pending-state store).

Security notes:
* Tokens expire after ``SESSION_TIMEOUT_SECONDS`` (default 24 h).
* The secret is never logged and never sent to the frontend; only the
  signed token travels (HttpOnly cookie + ``Authorization: Bearer``).
* Signature comparison is constant-time; malformed/expired tokens fail
  closed (``None``).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.user_context import UserIdentity


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: Dict[str, Any], secret: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def _verify(token: str, secret: str) -> Optional[Dict[str, Any]]:
    try:
        header_b64, body_b64, sig_b64 = token.strip().split(".")
        signing_input = f"{header_b64}.{body_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(body_b64).decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        exp = payload.get("exp")
        if exp is not None and time.time() > float(exp):
            return None
        return payload
    except Exception:
        return None


def _get_secret() -> str:
    secret = settings.SESSION_SECRET
    if not secret or len(secret) < 32:
        raise ValueError(
            "SESSION_SECRET is not configured (or is shorter than 32 characters). "
            "Set a long random SESSION_SECRET to enable Google sign-in sessions."
        )
    return secret


def create_session_token(user: UserIdentity) -> str:
    """Mint a session JWT for a signed-in Google user."""
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": user.sub,
        "email": user.email,
        "name": user.name,
        "iat": now,
        "exp": now + settings.SESSION_TIMEOUT_SECONDS,
        "purpose": "session",
    }
    return _sign(payload, _get_secret())


def verify_session_token(token: str) -> Optional[UserIdentity]:
    """Verify a session JWT; returns the user or None."""
    try:
        secret = _get_secret()
    except ValueError:
        return None
    payload = _verify(token, secret)
    if not payload or payload.get("purpose") != "session" or not payload.get("sub"):
        return None
    return UserIdentity(
        sub=str(payload["sub"]),
        email=payload.get("email"),
        name=payload.get("name"),
    )


def create_oauth_state_token(state: str, code_verifier: str, redirect_uri: str) -> str:
    """Sign the login-flow PKCE verifier + state into a short-lived cookie value.

    Stateless by design: Vercel serverless may cold-start between the
    login redirect and the callback, so the verifier must not live only in
    server memory.
    """
    now = int(time.time())
    payload: Dict[str, Any] = {
        "state": state,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "iat": now,
        "exp": now + 600,  # 10 minutes, same as the old in-memory STATE_TTL
        "purpose": "oauth-state",
    }
    return _sign(payload, _get_secret())


def verify_oauth_state_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify a signed OAuth-state cookie; returns its payload or None."""
    try:
        secret = _get_secret()
    except ValueError:
        return None
    payload = _verify(token, secret)
    if not payload or payload.get("purpose") != "oauth-state":
        return None
    if not payload.get("state") or not payload.get("code_verifier"):
        return None
    return payload
