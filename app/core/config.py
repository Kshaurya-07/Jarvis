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
    ACTION_LOG_FILE: Path = Path("./logs/actions.jsonl")

    # Security limits
    MAX_FILE_READ_BYTES: int = 1024 * 1024  # 1 MB max file read size
    MAX_REQUEST_LENGTH: int = 4096  # Max user input text length

    def resolve_paths(self) -> None:
        """Resolve and initialize runtime directories."""
        self.WORKSPACE_DIR = self.WORKSPACE_DIR.resolve()
        self.NOTES_DIR = self.NOTES_DIR.resolve()
        self.ACTION_LOG_FILE = self.ACTION_LOG_FILE.resolve()

        self.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        self.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        self.ACTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.resolve_paths()
