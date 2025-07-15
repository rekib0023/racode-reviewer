import logging
import sys

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "default",
            "stream": sys.stdout,
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "default",
            "filename": "app.log",
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "fastapi": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "app": {  # Logger for the application
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
}


def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
    # Optionally, integrate with Pydantic settings for log level
    from app.core.config import settings

    logging.getLogger("app").setLevel(settings.LOG_LEVEL.upper())
    logging.getLogger("uvicorn").setLevel(settings.LOG_LEVEL.upper())
    logging.getLogger("fastapi").setLevel(settings.LOG_LEVEL.upper())
    logging.getLogger("root").setLevel(settings.LOG_LEVEL.upper())
