from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core application settings
    REPO_CLONE_DIR: str = "./repos"
    LANCEDB_PATH: str = "./lancedb_data/db"
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    CHAT_MODEL_NAME: str = "qwen2.5-coder:7b"  # Default chat model for LLM

    # GitHub App credentials and webhook secret
    GITHUB_APP_ID: str
    GITHUB_PRIVATE_KEY: str  # Should be the content of the .pem file
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_APP_NAME: str

    # Optional: For sentence-transformers cache
    SENTENCE_TRANSFORMERS_HOME: Optional[str] = None

    # API Keys for external services (example, add if needed)
    # OPENAI_API_KEY: Optional[str] = None

    # Logging configuration
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Create a single instance of the settings to be used throughout the application
settings = Settings()
