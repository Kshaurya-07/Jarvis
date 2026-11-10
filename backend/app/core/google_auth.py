import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import httpx
import keyring

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

from app.core.config import settings
from app.core.logger import app_logger

# Service name for OS Credential Locker / keyring
KEYRING_SERVICE_NAME = "Jarvis_Google_OAuth"
KEYRING_USERNAME = "default_account"
STATE_TTL_SECONDS = 600.0  # 10 minutes


class GoogleAuthError(Exception):
    """Base exception for Google OAuth errors."""


class GoogleAuthRequiredError(GoogleAuthError):
    """Raised when an operation requires an active Google account connection."""


class GoogleTokenRevokedError(GoogleAuthError):
    """Raised when the stored OAuth token has been revoked or expired."""


class GoogleConfigError(GoogleAuthError):
    """Raised when Google OAuth credentials (client ID/secret) are missing."""


@dataclass
class OAuthPendingState:
    state: str
    code_verifier: str
    created_at: float
    redirect_uri: str
    purpose: str = "gmail"  # "gmail" (read-only Gmail/Calendar) or "login" (sign-in)


class GoogleAuthManager:
    """
    Manages Google OAuth 2.0 authorization code flow with PKCE,
    anti-CSRF state verification, and secure OS credential storage.
    """

    def __init__(self):
        self._pending_states: Dict[str, OAuthPendingState] = {}
        self._cached_creds: Optional[Credentials] = None

    def _purge_expired_states(self) -> None:
        """Purge states older than STATE_TTL_SECONDS."""
        now = time.time()
        expired = [s for s, state_obj in self._pending_states.items() if now - state_obj.created_at > STATE_TTL_SECONDS]
        for s in expired:
            self._pending_states.pop(s, None)

    @staticmethod
    def generate_pkce_pair() -> Tuple[str, str]:
        """
        Generate a high-entropy PKCE code_verifier and S256 code_challenge
        according to RFC 7636.
        """
        # 64 random bytes produces ~86 URL-safe characters (valid range: 43-128)
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return code_verifier, code_challenge

    def create_authorization_url(self, redirect_uri: Optional[str] = None) -> Tuple[str, str]:
        """
        Create a Google OAuth 2.0 authorization URL with PKCE (S256) and state.
        Returns: (authorization_url, state)
        """
        if not settings.GOOGLE_CLIENT_ID:
            raise GoogleConfigError(
                "Google Client ID is not configured. Please set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET in your .env file. See README.md for setup instructions."
            )

        self._purge_expired_states()

        effective_redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
        code_verifier, code_challenge = self.generate_pkce_pair()
        state = secrets.token_urlsafe(32)

        self._pending_states[state] = OAuthPendingState(
            state=state,
            code_verifier=code_verifier,
            created_at=time.time(),
            redirect_uri=effective_redirect_uri,
        )

        scopes_str = " ".join(settings.GOOGLE_OAUTH_SCOPES)
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": effective_redirect_uri,
            "response_type": "code",
            "scope": scopes_str,
            "access_type": "offline",
            "prompt": "consent",  # Ensures refresh token is issued
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        query_parts = [f"{k}={httpx.URL('', params={k: v}).query.decode('utf-8')}" for k, v in params.items()]
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{'&'.join(query_parts)}"
        return auth_url, state

    # -- Phase 12: Google sign-in (login), separate from Gmail/Calendar --
    def create_login_authorization_url(self) -> tuple:
        """Build the Google sign-in URL (scopes: openid/email/profile only).

        Returns (auth_url, state, code_verifier, redirect_uri). The caller
        stores state+verifier in a *signed cookie* (see app.core.session),
        not in server memory, so the flow survives Vercel cold starts.
        No Google password is ever seen or stored — Google handles sign-in.
        """
        if not settings.GOOGLE_CLIENT_ID:
            raise GoogleConfigError(
                "Google Client ID is not configured. Set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET in your environment. See README.md."
            )
        redirect_uri = settings.GOOGLE_LOGIN_REDIRECT_URI
        code_verifier, code_challenge = self.generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        scopes_str = " ".join(settings.GOOGLE_LOGIN_SCOPES)
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes_str,
            "access_type": "online",
            "prompt": "select_account",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        query_parts = [f"{k}={httpx.URL('', params={k: v}).query.decode('utf-8')}" for k, v in params.items()]
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{'&'.join(query_parts)}"
        return auth_url, state, code_verifier, redirect_uri

    def exchange_login_code(self, code: str, code_verifier: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange a login authorization code for the user's Google identity.

        Verifies Google's ID token (signature, audience, expiry) with
        ``google.oauth2.id_token`` and returns ``sub``/``email``/``name``.
        The access token is discarded — sign-in needs no Gmail/Calendar
        access, and nothing is stored in keyring for login.
        """
        if not settings.GOOGLE_CLIENT_ID:
            raise GoogleConfigError("GOOGLE_CLIENT_ID is not configured.")
        data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if settings.GOOGLE_CLIENT_SECRET:
            data["client_secret"] = settings.GOOGLE_CLIENT_SECRET
        try:
            with httpx.Client(trust_env=False, timeout=10.0) as client:
                resp = client.post("https://oauth2.googleapis.com/token", data=data)
                if resp.status_code != 200:
                    err_json = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    err_desc = err_json.get("error_description", resp.text)
                    raise GoogleAuthError(f"Token exchange failed (HTTP {resp.status_code}): {err_desc}")
                token_data = resp.json()
        except httpx.RequestError as exc:
            raise GoogleAuthError(f"Network error during token exchange: {str(exc)}") from exc

        id_token = token_data.get("id_token")
        if not id_token:
            raise GoogleAuthError("Google did not return an ID token for sign-in.")
        try:
            from google.oauth2 import id_token as google_id_token

            claims = google_id_token.verify_oauth2_token(
                id_token, GoogleAuthRequest(), settings.GOOGLE_CLIENT_ID
            )
        except Exception as exc:
            raise GoogleAuthError(f"Google ID token verification failed: {exc}") from exc
        sub = claims.get("sub")
        if not sub:
            raise GoogleAuthError("Google ID token has no user ID (sub).")
        return {
            "sub": sub,
            "email": claims.get("email"),
            "name": claims.get("name"),
            "picture": claims.get("picture"),
        }

    def validate_and_consume_state(self, state: str) -> OAuthPendingState:
        """
        Validate and consume the state parameter to prevent replay attacks and CSRF.
        """
        self._purge_expired_states()
        if not state or state not in self._pending_states:
            raise GoogleAuthError(
                "Invalid or expired OAuth state parameter. Possible CSRF attack or session expired."
            )
        pending = self._pending_states.pop(state)
        if time.time() - pending.created_at > STATE_TTL_SECONDS:
            raise GoogleAuthError("OAuth state has expired. Please initiate authorization again.")
        return pending

    def exchange_code(self, code: str, state: str) -> Dict[str, Any]:
        """
        Exchange the authorization code for access and refresh tokens using PKCE verifier.
        Stores tokens securely in the OS credential store or opt-in fallback.
        """
        pending = self.validate_and_consume_state(state)

        if not settings.GOOGLE_CLIENT_ID:
            raise GoogleConfigError("GOOGLE_CLIENT_ID is not configured.")

        data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "code": code,
            "code_verifier": pending.code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": pending.redirect_uri,
        }
        if settings.GOOGLE_CLIENT_SECRET:
            data["client_secret"] = settings.GOOGLE_CLIENT_SECRET

        try:
            with httpx.Client(trust_env=False, timeout=10.0) as client:
                resp = client.post("https://oauth2.googleapis.com/token", data=data)
                if resp.status_code != 200:
                    err_json = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    err_desc = err_json.get("error_description", resp.text)
                    raise GoogleAuthError(f"Token exchange failed (HTTP {resp.status_code}): {err_desc}")
                token_data = resp.json()
        except httpx.RequestError as exc:
            raise GoogleAuthError(f"Network error during token exchange: {str(exc)}") from exc

        # Extract email if id_token is returned (without adding userinfo scope)
        account_email = self._extract_email_from_id_token(token_data.get("id_token"))

        # Prepare payload to store
        payload = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "scopes": settings.GOOGLE_OAUTH_SCOPES,
            "account_email": account_email,
            "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "expires_in": token_data.get("expires_in"),
        }

        # If refresh token was not returned (e.g. user already authorized previously without prompt=consent),
        # try to preserve existing refresh token if available
        if not payload.get("refresh_token"):
            existing = self._load_raw_payload()
            if existing and existing.get("refresh_token"):
                payload["refresh_token"] = existing["refresh_token"]

        self._save_raw_payload(payload)
        self._cached_creds = None
        app_logger.info("Successfully connected Google account with read-only scopes.")

        return {
            "status": "connected",
            "account_email": account_email,
            "scopes": settings.GOOGLE_OAUTH_SCOPES,
            "storage_backend": self._get_storage_backend_name(),
        }

    def _extract_email_from_id_token(self, id_token: Optional[str]) -> Optional[str]:
        """Safely extract the email claim from an unverified JWT payload for display."""
        if not id_token or not isinstance(id_token, str):
            return None
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        try:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
            return claims.get("email")
        except Exception:
            return None

    def _get_storage_backend_name(self) -> str:
        """Return human-readable description of current storage backend."""
        try:
            kr = keyring.get_keyring()
            if kr and kr.priority > 0:
                return f"OS Credential Store ({kr.__class__.__name__})"
        except Exception:
            pass
        return "Protected Local File (Fallback)"

    def _save_raw_payload(self, payload: Dict[str, Any]) -> None:
        """
        Store token payload securely.
        Uses OS credential store via keyring first. If unavailable, checks fallback opt-in.
        """
        serialized = json.dumps(payload)
        saved = False

        # 1. Try OS Credential Store (keyring)
        try:
            kr = keyring.get_keyring()
            if kr and kr.priority > 0:
                keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, serialized)
                saved = True
        except Exception as e:
            app_logger.warning("OS credential store unavailable or failed: %s", e)

        if saved:
            return

        # 2. Check Fallback Opt-in
        if not settings.GOOGLE_CREDENTIAL_FALLBACK_OPT_IN:
            raise RuntimeError(
                "Operating system credential store is unavailable on this environment. "
                "For security, falling back to local file storage requires explicit user opt-in. "
                "Set GOOGLE_CREDENTIAL_FALLBACK_OPT_IN=true in your environment or .env file to enable protected local token storage."
            )

        # Write to protected file
        fallback_path = settings.GOOGLE_FALLBACK_TOKEN_FILE
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Write with restricted permissions
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = 0o600  # Read/Write by owner only
            fd = os.open(str(fallback_path), flags, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            app_logger.info("Saved Google tokens to protected fallback file: %s", fallback_path)
        except Exception as e:
            raise RuntimeError(f"Failed to write to fallback token file: {e}") from e

    def _load_raw_payload(self) -> Optional[Dict[str, Any]]:
        """Load token payload from OS credential store or fallback file."""
        # 1. Try keyring
        try:
            kr = keyring.get_keyring()
            if kr and kr.priority > 0:
                val = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
                if val:
                    return json.loads(val)
        except Exception as e:
            app_logger.debug("Keyring retrieval error: %s", e)

        # 2. Try fallback file if opt-in enabled or file exists
        fallback_path = settings.GOOGLE_FALLBACK_TOKEN_FILE
        if fallback_path.exists():
            try:
                with open(fallback_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                app_logger.warning("Failed to read fallback token file: %s", e)
        return None

    def _delete_raw_payload(self) -> None:
        """Delete credentials from both keyring and fallback file."""
        # 1. Keyring
        try:
            keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
        except Exception:
            pass

        # 2. Fallback file
        try:
            fallback_path = settings.GOOGLE_FALLBACK_TOKEN_FILE
            if fallback_path.exists():
                fallback_path.unlink()
        except Exception:
            pass

    def is_connected(self) -> bool:
        """Check if an authorized Google account is connected."""
        payload = self._load_raw_payload()
        return bool(payload and (payload.get("refresh_token") or payload.get("access_token")))

    def get_credentials(self) -> Credentials:
        """
        Retrieve valid Google OAuth Credentials, automatically refreshing if expired.
        Raises GoogleAuthRequiredError if not connected.
        Raises GoogleTokenRevokedError if refresh fails.
        """
        payload = self._load_raw_payload()
        if not payload or not (payload.get("refresh_token") or payload.get("access_token")):
            raise GoogleAuthRequiredError(
                "Google account is not connected. Please connect via /api/auth/google/url."
            )

        creds = Credentials(
            token=payload.get("access_token"),
            refresh_token=payload.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=payload.get("client_id") or settings.GOOGLE_CLIENT_ID,
            client_secret=payload.get("client_secret") or settings.GOOGLE_CLIENT_SECRET,
            scopes=payload.get("scopes") or settings.GOOGLE_OAUTH_SCOPES,
        )

        # Refresh if expired
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(GoogleAuthRequest())
                    # Update saved access token
                    payload["access_token"] = creds.token
                    self._save_raw_payload(payload)
                except Exception as exc:
                    self._delete_raw_payload()
                    self._cached_creds = None
                    raise GoogleTokenRevokedError(
                        f"Google OAuth token has expired or been revoked: {str(exc)}. "
                        "Please reconnect your account via /api/auth/google/url."
                    ) from exc
            else:
                raise GoogleAuthRequiredError(
                    "Google OAuth credentials are invalid or missing a refresh token. "
                    "Please reconnect via /api/auth/google/url."
                )

        return creds

    def disconnect(self) -> Dict[str, Any]:
        """
        Disconnect Google account: revoke the token with Google servers and
        erase credentials from the OS credential store and fallback storage.
        """
        payload = self._load_raw_payload()
        token_to_revoke = None
        if payload:
            token_to_revoke = payload.get("refresh_token") or payload.get("access_token")

        # Attempt remote revocation
        revoked_remotely = False
        if token_to_revoke:
            try:
                with httpx.Client(trust_env=False, timeout=5.0) as client:
                    resp = client.post(
                        "https://oauth2.googleapis.com/revoke",
                        params={"token": token_to_revoke},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    revoked_remotely = (resp.status_code == 200)
            except Exception as e:
                app_logger.warning("Google token revocation request error: %s", e)

        # Delete local credentials
        self._delete_raw_payload()
        self._cached_creds = None

        return {
            "status": "disconnected",
            "message": "Google account successfully disconnected and local tokens deleted.",
            "revoked_remotely": revoked_remotely,
        }

    def get_status(self) -> Dict[str, Any]:
        """Return public status of Google OAuth integration."""
        payload = self._load_raw_payload()
        if not payload or not (payload.get("refresh_token") or payload.get("access_token")):
            return {
                "connected": False,
                "account_email": None,
                "scopes": [],
                "storage_backend": self._get_storage_backend_name(),
                "connected_at": None,
                "read_only": True,
            }

        return {
            "connected": True,
            "account_email": payload.get("account_email"),
            "scopes": payload.get("scopes", settings.GOOGLE_OAUTH_SCOPES),
            "storage_backend": self._get_storage_backend_name(),
            "connected_at": payload.get("connected_at"),
            "read_only": True,
        }


# Global singleton manager
google_auth_manager = GoogleAuthManager()
