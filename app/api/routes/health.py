"""
Health check endpoints.

These endpoints provide basic health and status information about the API.
"""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter()


@router.get("/health")
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Simple health check endpoint.

    Returns status information about the API, including version and environment.
    """
    return {
        "status": "healthy",
        "message": "Code Reviewer API is running.",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }
