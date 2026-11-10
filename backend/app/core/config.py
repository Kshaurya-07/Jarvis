from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


# .env lives at the repo root, but the server runs from backend/ (where `app`
# is a top-level package), so a plain env_file=".env" only loads when the
# working directory happens to be the repo root. Anchor the repo-root .env to
# this file's location so the documented `copy .env.example .env` flow works
# from either directory; a .env in the working directory is read after it
# and overrides it (pydantic-settings: later files win).
_REPO_ROOT = Path(__file__).resolve().parents[3]


class ConfigurationError(Exception):
    """Raised when application configuration contains unsafe or fatal values."""


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings (always bind to localhost by default)
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    ALLOW_REMOTE_ACCESS: bool = False  # Strictly local-only by default

    # --- Cloud-first mode (Phase 12) -------------------------------------
    # CLOUD_MODE=true is how the backend runs on Vercel serverless:
    # Google sign-in is mandatory for every AI/data endpoint, and all user
    # data is namespaced per Google account. Local
    # mode (CLOUD_MODE=false, the default) keeps the old behaviour: loopback
    # requests from the owner's own laptop are trusted without sign-in, so
    # local development and the existing test suite keep working.
    CLOUD_MODE: bool = False
    # Secret used to sign Jarvis session JWTs (HS256) and, as a fallback, to
    # derive the BYOK encryption key. REQUIRED in cloud mode; generate a
    # long random value. Never
    # commit it, never log it. Rotating it signs everyone out and makes
    # previously stored BYOK keys undecryptable (users re-enter their key).
    SESSION_SECRET: Optional[str] = None
    SESSION_TIMEOUT_SECONDS: int = 86400  # 24 hours per sign-in session
    # Optional dedicated Fernet key (base64 urlsafe 32 bytes) for encrypting
    # stored BYOK Gemini keys. If unset, one is derived from SESSION_SECRET.
    KEY_ENCRYPTION_KEY: Optional[str] = None
    # Google sign-in (login) flow. Separate purpose from the read-only
    # Gmail/Calendar OAuth below: scopes are only openid/email/profile.
    GOOGLE_LOGIN_REDIRECT_URI: str = "http://127.0.0.1:8000/api/auth/login/callback"
    GOOGLE_LOGIN_SCOPES: list[str] = ["openid", "email", "profile"]
    # Public frontend origin users are sent back to after Google sign-in.
    FRONTEND_URL: str = "https://jarvis-kumar-shaurya.vercel.app"
    # Per-user Gemini usage caps (BYOK keys are the user's own, so these are
    # abuse/fat-finger guards, not billing controls). In-memory only: they
    # reset on restart/redeploy and do not sync across instances.
    GEMINI_CALLS_PER_USER_PER_HOUR: int = 30
    GEMINI_CALLS_PER_USER_PER_DAY: int = 100

    # --- External storage (Vercel serverless) ---------------------------
    # DATABASE_URL: Postgres connection string (Neon — see README).
    # REQUIRED in production on Vercel: serverless functions have no
    # persistent filesystem, so all per-user data (notes, memories,
    # reminders, encrypted BYOK keys, chat history, action log) lives in
    # Postgres. When unset, Jarvis uses local per-user files instead, so
    # local `uvicorn` dev and tests work with zero setup.
    DATABASE_URL: Optional[str] = None

    # Gemini API settings
    # NOTE (Phase 12, BYOK): GEMINI_API_KEY is NO LONGER USED. Every user
    # brings their own Gemini key, stored encrypted per user. A server/owner
    # key is deliberately not a fallback: one shared key would let any
    # signed-in user spend the owner's quota. Leave this unset.
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Storage paths
    WORKSPACE_DIR: Path = Path("./workspace")
    NOTES_DIR: Path = Path("./notes")
    SCREENSHOTS_DIR: Path = Path("./screenshots")
    DATA_DIR: Path = Path("./data")
    BACKUPS_DIR: Path = Path("./backups")
    REMINDERS_FILE: Path = Path("./data/reminders.json")
    MEMORIES_FILE: Path = Path("./data/memories.json")
    ACTION_LOG_FILE: Path = Path("./logs/actions.jsonl")

    # Feature Flags & Settings
    MEMORY_ENABLED: bool = True

    # Search Provider Settings (Phase 5)
    SEARCH_PROVIDER: str = "tavily"  # "tavily", "google_custom_search", or "brave"
    SEARCH_API_KEY: Optional[str] = None
    SEARCH_ENGINE_ID: Optional[str] = None  # Google Custom Search CX
    SEARCH_TIMEOUT_SECONDS: float = 8.0
    MAX_SEARCH_RESULTS: int = 5
    MAX_SEARCH_QUERY_LENGTH: int = 200

    # Google OAuth & Integrations (Phase 6 - Read-Only Gmail & Calendar)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/api/auth/google/callback"
    GOOGLE_CREDENTIAL_FALLBACK_OPT_IN: bool = False
    GOOGLE_FALLBACK_TOKEN_FILE: Path = Path("./data/protected_google_token.json")
    GOOGLE_OAUTH_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    MAX_GMAIL_RESULTS: int = 10
    MAX_CALENDAR_RESULTS: int = 25

    # Security limits & Rate limits (Phase 9 Hardening)
    MAX_FILE_READ_BYTES: int = 1024 * 1024  # 1 MB max file read size
    MAX_REQUEST_LENGTH: int = 4096  # Max user input text length
    MAX_REQUEST_BODY_BYTES: int = 2 * 1024 * 1024  # 2 MB max request body payload
    MAX_PAGE_TEXT_CHARS: int = 50000  # 50,000 max characters from browser page
    CONFIRMATION_TIMEOUT_SECONDS: int = 300  # 5 minutes validity for confirmations
    AUTH_FAILURE_RATE_LIMIT: int = 5  # Max authentication failures before temporary block
    AUTH_FAILURE_WINDOW_SECONDS: int = 60  # Rate limit window in seconds

    # Remote Pairing & Tailscale Private Connection (Phase 11)
    ALLOWED_ORIGINS: list[str] = []  # Extra origins permitted in addition to verified Vercel production/preview
    TAILSCALE_HOST: Optional[str] = None  # Optional explicit Tailscale machine domain (e.g. laptop.tailnet.ts.net)
    REMOTE_PAIRING_CODE_TIMEOUT_SECONDS: int = 300  # 5 minutes for short-lived pairing code
    REMOTE_SESSION_TIMEOUT_SECONDS: int = 3600  # 1 hour for in-memory session token
    PAIRING_RATE_LIMIT: int = 5  # Max 5 failed pairing attempts
    PAIRING_RATE_LIMIT_WINDOW_SECONDS: int = 60  # 60s window for pairing rate limit

    def resolve_paths(self) -> None:
        """Resolve and initialize runtime directories."""
        self.WORKSPACE_DIR = self.WORKSPACE_DIR.resolve()
        self.NOTES_DIR = self.NOTES_DIR.resolve()
        self.SCREENSHOTS_DIR = self.SCREENSHOTS_DIR.resolve()
        self.DATA_DIR = self.DATA_DIR.resolve()
        self.BACKUPS_DIR = self.BACKUPS_DIR.resolve()
        self.REMINDERS_FILE = self.REMINDERS_FILE.resolve()
        self.MEMORIES_FILE = self.MEMORIES_FILE.resolve()
        self.GOOGLE_FALLBACK_TOKEN_FILE = self.GOOGLE_FALLBACK_TOKEN_FILE.resolve()
        self.ACTION_LOG_FILE = self.ACTION_LOG_FILE.resolve()

        # Best-effort only: Vercel serverless functions run on a read-only
        # filesystem (only /tmp is writable), and the local data dirs are
        # not in the deployment at all. Creating them must never crash the
        # import — in cloud mode all user data lives in Postgres anyway.
        # Locally these mkdirs succeed exactly as before.
        for _d in (
            self.WORKSPACE_DIR,
            self.NOTES_DIR,
            self.SCREENSHOTS_DIR,
            self.DATA_DIR,
            self.BACKUPS_DIR,
            self.ACTION_LOG_FILE.parent,
        ):
            try:
                _d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def validate_configuration(self) -> list[str]:
        """
        Validate application configuration for security and release readiness.
        Raises ConfigurationError for fatal misconfigurations;
        returns a list of informational warnings for non-fatal states.
        """
        warnings: list[str] = []

        # 1. Localhost binding security check
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.HOST not in loopback_hosts and not self.ALLOW_REMOTE_ACCESS and not self.CLOUD_MODE:
            raise ConfigurationError(
                f"Security Violation: Backend is configured to bind to '{self.HOST}'. "
                "Jarvis must bind strictly to 127.0.0.1 (localhost) by default to prevent "
                "unauthorized network access. Set ALLOW_REMOTE_ACCESS=true to explicitly override."
            )

        # 1b. Cloud mode: sign-in must be
        # possible — a missing/short SESSION_SECRET is a loud warning, not a
        # fatal error, so local smoke tests can still boot without one.
        if self.CLOUD_MODE:
            if not self.SESSION_SECRET or len(self.SESSION_SECRET) < 32:
                warnings.append(
                    "Warning: CLOUD_MODE is on but SESSION_SECRET is missing or shorter "
                    "than 32 characters. Google sign-in sessions cannot be issued until "
                    "a long random SESSION_SECRET is set."
                )
            if not self.DATABASE_URL:
                warnings.append(
                    "Warning: CLOUD_MODE is on but DATABASE_URL is not set. User data "
                    "will be written to the local filesystem, which DOES NOT PERSIST on "
                    "Vercel serverless — set DATABASE_URL (Neon Postgres) before "
                    "deploying, or data will be lost between invocations."
                )
            # NOTE: no HOST check here. On Vercel serverless the platform
            # owns the listener — HOST binding does not apply — so a
            # loopback HOST default is expected and must not warn.

        # 2. Port validation
        if not (1 <= self.PORT <= 65535):
            raise ConfigurationError(f"Invalid PORT {self.PORT}: port must be between 1 and 65535.")

        # 3. Search provider validation
        allowed_providers = {"tavily", "google_custom_search", "brave"}
        if self.SEARCH_PROVIDER not in allowed_providers:
            raise ConfigurationError(
                f"Invalid SEARCH_PROVIDER '{self.SEARCH_PROVIDER}'. "
                f"Supported providers: {', '.join(sorted(allowed_providers))}."
            )

        # 4. Informational checks
        if self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip() not in ("", "your_gemini_api_key_here"):
            warnings.append(
                "Notice: GEMINI_API_KEY is set but is IGNORED since Phase 12 (BYOK). "
                "Each user brings their own Gemini key; there is no server/owner key "
                "path. Remove it from your environment to avoid confusion."
            )

        if self.GOOGLE_CLIENT_ID and not self.GOOGLE_CLIENT_SECRET:
            warnings.append(
                "Warning: GOOGLE_CLIENT_ID is defined but GOOGLE_CLIENT_SECRET is missing. "
                "Google OAuth login will not complete without client secret."
            )

        return warnings


settings = Settings()
settings.resolve_paths()
