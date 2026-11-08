from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Raised when application configuration contains unsafe or fatal values."""
    pass


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings (always bind to localhost by default)
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    ALLOW_REMOTE_ACCESS: bool = False  # Strictly local-only by default

    # Gemini API settings
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

        self.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        self.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        self.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        self.ACTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def validate_configuration(self) -> list[str]:
        """
        Validate application configuration for security and release readiness.
        Raises ConfigurationError for fatal misconfigurations;
        returns a list of informational warnings for non-fatal states.
        """
        warnings: list[str] = []

        # 1. Localhost binding security check
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.HOST not in loopback_hosts and not self.ALLOW_REMOTE_ACCESS:
            raise ConfigurationError(
                f"Security Violation: Backend is configured to bind to '{self.HOST}'. "
                "Jarvis must bind strictly to 127.0.0.1 (localhost) by default to prevent "
                "unauthorized network access. Set ALLOW_REMOTE_ACCESS=true to explicitly override."
            )

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
        if not self.GEMINI_API_KEY or self.GEMINI_API_KEY.strip() in ("", "your_gemini_api_key_here"):
            warnings.append(
                "Notice: GEMINI_API_KEY is not configured. AI reasoning, chat, and Gemini tool selection "
                "will be offline until an API key is provided in .env."
            )

        if self.GOOGLE_CLIENT_ID and not self.GOOGLE_CLIENT_SECRET:
            warnings.append(
                "Warning: GOOGLE_CLIENT_ID is defined but GOOGLE_CLIENT_SECRET is missing. "
                "Google OAuth login will not complete without client secret."
            )

        return warnings


settings = Settings()
settings.resolve_paths()
