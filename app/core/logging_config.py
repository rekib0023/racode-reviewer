"""
Logging configuration module for the application.

This module provides a centralized logging configuration system that:
1. Sets up both console and file logging with rotation
2. Integrates with the application configuration
3. Allows for consistent log formatting across the application
4. Provides a structured JSON formatter for better log parsing
"""

import json
import logging
import logging.config
import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

# Import settings without circular dependency
from app.core.config import get_settings


class StructuredJSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs in JSON format for better parsing.

    This formatter creates structured JSON logs with consistent fields for
    timestamp, level, name, message, and additional contextual data.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include any extra attributes from record
        for key, value in record.__dict__.items():
            if key not in [
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ]:
                log_data[key] = value

        return json.dumps(log_data)


@lru_cache()
def get_logging_config() -> Dict[str, Any]:
    """
    Create and return a cached logging configuration dictionary.

    This function implements the Singleton pattern using lru_cache to ensure
    that the logging configuration is consistent throughout the application.

    Returns:
        Dict[str, Any]: The logging configuration dictionary
    """
    settings = get_settings()

    # Ensure log directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "app.core.logging_config.StructuredJSONFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "default",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "default",
                "filename": os.path.join("logs", "app.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10 MB
                "backupCount": 10,
                "encoding": "utf-8",
            },
            "json_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "json",
                "filename": os.path.join("logs", "app.json.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10 MB
                "backupCount": 10,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": settings.LOG_LEVEL,
                "propagate": False,
            },
            "fastapi": {
                "handlers": ["console", "file"],
                "level": settings.LOG_LEVEL,
                "propagate": False,
            },
            "app": {  # Logger for the application
                "handlers": ["console", "file", "json_file"],
                "level": settings.LOG_LEVEL,
                "propagate": False,
            },
        },
        "root": {
            "level": settings.LOG_LEVEL,
            "handlers": ["console", "file"],
        },
    }


def setup_logging() -> None:
    """
    Configure the logging system for the application.

    This function initializes logging with the configuration from get_logging_config
    and ensures all loggers use the configured log levels from settings.
    """
    logging_config = get_logging_config()
    logging.config.dictConfig(logging_config)
    logger = logging.getLogger("app")
    logger.debug("Logging system initialized")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    This is a convenience function for getting a logger with the proper namespace.

    Args:
        name: The name for the logger, usually __name__ from the calling module

    Returns:
        logging.Logger: Configured logger instance
    """
    if name.startswith("app."):
        return logging.getLogger(name)
    return logging.getLogger(f"app.{name}")
