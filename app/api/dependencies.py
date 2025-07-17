"""
Dependency injection module for FastAPI.

This module provides dependencies that can be injected into route functions
using FastAPI's dependency injection system.
"""

from app.core.config import get_settings  # noqa: F401

# Re-export the get_settings function for use in route dependencies
# This pattern allows for easier mocking in tests
