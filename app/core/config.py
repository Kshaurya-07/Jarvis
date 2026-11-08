from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Gemini API settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Storage paths
    WORKSPACE_DIR: Path = Path("./workspace")
    NOTES_DIR: Path = Path("./notes")
    SCREENSHOTS_DIR: Path = Path("./screenshots")
    DATA_DIR: Path = Path("./data")
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

    # Security limits
    MAX_FILE_READ_BYTES: int = 1024 * 1024  # 1 MB max file read size
    MAX_REQUEST_LENGTH: int = 4096  # Max user input text length
    MAX_PAGE_TEXT_CHARS: int = 50000  # 50,000 max characters from browser page
    CONFIRMATION_TIMEOUT_SECONDS: int = 300  # 5 minutes validity for confirmations

    def resolve_paths(self) -> None:
        """Resolve and initialize runtime directories."""
        self.WORKSPACE_DIR = self.WORKSPACE_DIR.resolve()
        self.NOTES_DIR = self.NOTES_DIR.resolve()
        self.SCREENSHOTS_DIR = self.SCREENSHOTS_DIR.resolve()
        self.DATA_DIR = self.DATA_DIR.resolve()
        self.REMINDERS_FILE = self.REMINDERS_FILE.resolve()
        self.MEMORIES_FILE = self.MEMORIES_FILE.resolve()
        self.ACTION_LOG_FILE = self.ACTION_LOG_FILE.resolve()

        self.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        self.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        self.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.ACTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.resolve_paths()
