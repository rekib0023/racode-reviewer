"""
Configuration module implementing the Singleton pattern for application settings.

This module provides a centralized configuration management system using Pydantic Settings.
Settings are loaded from environment variables and/or .env files, with type validation.
The Settings class is implemented as a Singleton to ensure consistent configuration
across the application.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings using Pydantic BaseSettings.

    This class defines all configuration parameters for the application with
    appropriate default values and type annotations. Configuration values can be
    overridden by environment variables or values in a .env file.

    Attributes:
        REPO_CLONE_DIR: Directory where Git repositories are cloned
        LANCEDB_PATH: Path to LanceDB storage
        EMBEDDING_MODEL_NAME: Name of the embedding model to use
        CHAT_MODEL_NAME: Name of the chat model for LLM operations
        SENTENCE_TRANSFORMERS_HOME: Optional cache directory for sentence transformers
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        WEBHOOK_URL: URL for webhook notifications
        ENVIRONMENT: Environment configuration (development, staging, production)
    """

    # Core application settings
    REPO_CLONE_DIR: str = "./repos"
    LANCEDB_PATH: str = "./lancedb_data/db"
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    CHAT_MODEL_NAME: str = "qwen2.5-coder:7b"  # Default chat model for LLM

    # Environment configuration
    ENVIRONMENT: str = "development"  # Options: development, staging, production

    # Logging configuration
    LOG_LEVEL: str = "INFO"

    # External service URLs
    WEBHOOK_URL: str = ""

    # Optional: For sentence-transformers cache
    SENTENCE_TRANSFORMERS_HOME: Optional[str] = None

    # Optional: For OpenAI API if using
    # OPENAI_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Create and return a cached instance of the Settings class.

    This function implements the Singleton pattern using lru_cache to ensure
    that only one instance of Settings is created and reused throughout the
    application lifecycle.

    Returns:
        Settings: The singleton instance of application settings
    """
    return Settings()


# Create a single instance of the settings to be used throughout the application
# This maintains backward compatibility with existing code
settings = get_settings()
