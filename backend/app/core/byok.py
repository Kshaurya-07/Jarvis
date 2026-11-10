"""Bring Your Own Key (BYOK) — per-user Gemini API keys (Phase 12).

Design (decided, and documented in the README):
* **No server/owner Gemini key path at all.** Every user signs in with
  Google, then pastes *their own* Gemini key (free from Google AI Studio)
  in Settings. That key — and only that key — pays for that user's Gemini
  calls. There is nothing for another user to exhaust, and the owner has
  no API bill. ``GEMINI_API_KEY`` in the environment is ignored.
* Keys are stored **encrypted at rest** (Fernet, AES-128-CBC + HMAC) via
  the active :class:`UserStore` — Postgres ``BYTEA`` in production, a
  ``0600`` file per user locally. The encryption key comes from
  ``KEY_ENCRYPTION_KEY`` when set, otherwise it is derived from
  ``SESSION_SECRET`` (PBKDF2-HMAC-SHA256, 200k iterations). Rotating the
  secret/key invalidates stored keys; users simply re-enter theirs.
* Keys are **never logged, never returned to the frontend** (only a masked
  hint like ``…aB3x`` plus created date), and never leave the server
  except inside the HTTPS call to Google's Gemini API for that user.
* ``validate_user_key`` checks a key against Google's models endpoint
  (no generation call, no charge beyond the free list call) so the UI can
  say "key valid / invalid" before the first chat.
"""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import re
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logger import app_logger
from app.core.store import get_user_store
from app.core.user_context import UserIdentity, resolve_user


class ByokError(Exception):
    """Raised for BYOK configuration or key problems (message is user-safe)."""


def _encryption_key() -> bytes:
    """Return a Fernet key (base64 urlsafe 32 bytes)."""
    raw = (settings.KEY_ENCRYPTION_KEY or "").strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            if len(key) != 32:
                raise ValueError("KEY_ENCRYPTION_KEY must decode to 32 bytes.")
            return base64.urlsafe_b64encode(key)
        except Exception as exc:
            raise ByokError("KEY_ENCRYPTION_KEY is not a valid Fernet key.") from exc
    secret = (settings.SESSION_SECRET or "").strip()
    if not secret or len(secret) < 32:
        raise ByokError(
            "Cannot encrypt Gemini keys: set KEY_ENCRYPTION_KEY or a SESSION_SECRET "
            "of at least 32 characters."
        )
    derived = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), b"jarvis-byok-v1", 200_000, dklen=32
    )
    return base64.urlsafe_b64encode(derived)


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(_encryption_key())


def _hint(api_key: str) -> str:
    return f"…{api_key[-4:]}" if len(api_key) >= 4 else "…????"


# Gemini API key formats (both are real keys issued by Google AI Studio):
# * Classic keys: ``AIza`` + base64url chars (real ones are 39 chars total;
#   the check below is deliberately lenient on length — total ≥ 30 — so
#   near-format keys are not rejected on a counting technicality).
# * Auth keys (all keys created in AI Studio since 2026-05-28): ``AQ.`` +
#   40-60 base64url chars. These are service-account-bound "auth keys" and
#   work with the Gemini Developer API via the ``x-goog-api-key`` header and
#   the official SDKs, exactly like classic keys. Accepting only ``AIza``
#   rejected every new AI Studio key (live bug, 2026-11-11).
_CLASSIC_KEY_RE = re.compile(r"^AIza[0-9A-Za-z\-_]+$")
_AUTH_KEY_RE = re.compile(r"^AQ\.[0-9A-Za-z\-_]{40,60}$")


def validate_key_format(api_key: str) -> None:
    """Loose format check for a Gemini API key; raises ByokError.

    Accepts both the classic ``AIza…`` format and the newer ``AQ.…`` auth
    keys issued by Google AI Studio since 2026-05-28.
    """
    key = (api_key or "").strip()
    if len(key) < 30 or not (_CLASSIC_KEY_RE.match(key) or _AUTH_KEY_RE.match(key)):
        raise ByokError(
            "That does not look like a Gemini API key. Gemini keys start with "
            "'AIza' (older keys) or 'AQ.' (new Google AI Studio keys) — copy "
            "yours from Google AI Studio (see README)."
        )


def store_user_key(user: Optional[UserIdentity], api_key: str) -> Dict[str, Any]:
    """Encrypt and store a user's own Gemini key. Returns only the public hint."""
    u = resolve_user(user)
    validate_key_format(api_key)
    encrypted = _fernet().encrypt(api_key.strip().encode("utf-8"))
    get_user_store().save_key(u, encrypted, _hint(api_key.strip()))
    app_logger.info("Stored an encrypted Gemini key for user namespace %s.", u.namespace)
    return {"has_key": True, "hint": _hint(api_key.strip()), "valid": None}


def load_user_key(user: Optional[UserIdentity] = None) -> Optional[str]:
    """Decrypt and return a user's Gemini key, or None if none/corrupt."""
    u = resolve_user(user)
    encrypted = get_user_store().load_key(u)
    if not encrypted:
        return None
    try:
        return _fernet().decrypt(encrypted).decode("utf-8")
    except Exception:
        app_logger.warning("Stored Gemini key for user namespace %s could not be decrypted.", u.namespace)
        return None


def key_status(user: Optional[UserIdentity] = None) -> Dict[str, Any]:
    """Public key status: has_key + masked hint only. Never the key itself."""
    u = resolve_user(user)
    meta = get_user_store().key_meta(u)
    has_key = get_user_store().load_key(u) is not None
    return {
        "has_key": has_key,
        "hint": meta.get("hint") if meta else None,
        "created_at": meta.get("created_at") if meta else None,
        "valid": None,  # use POST /api/auth/key/validate for a live check
    }


def delete_user_key(user: Optional[UserIdentity] = None) -> bool:
    return get_user_store().delete_key(resolve_user(user))


def validate_user_key(user: Optional[UserIdentity] = None) -> Dict[str, Any]:
    """Live-check the stored key against Google's models endpoint.

    A ``GET /v1beta/models`` with the key in the ``x-goog-api-key`` header:
    200 -> valid, 400/401/403 -> invalid. No generation call is made, so
    this costs nothing beyond a free list call. The key is sent only to
    Google, over HTTPS, and never logged.
    """
    u = resolve_user(user)
    api_key = load_user_key(u)
    if not api_key:
        return {"has_key": False, "valid": False, "detail": "No Gemini key saved yet."}
    try:
        with httpx.Client(trust_env=False, timeout=10.0) as client:
            resp = client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": api_key},
                params={"pageSize": 1},
            )
    except httpx.RequestError as exc:
        return {"has_key": True, "valid": None, "detail": f"Could not reach Google to check the key: {exc}"}
    if resp.status_code == 200:
        return {"has_key": True, "valid": True, "detail": "Key works."}
    if resp.status_code in (400, 401, 403):
        return {"has_key": True, "valid": False,
                "detail": "Google rejected this key. Check it in AI Studio and paste it again."}
    return {"has_key": True, "valid": None, "detail": f"Google returned HTTP {resp.status_code}."}
