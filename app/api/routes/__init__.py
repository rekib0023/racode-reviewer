"""
API routes initialization.

This module aggregates all router modules into a single API router.
"""

from fastapi import APIRouter

from app.api.routes.github import router as github_router
from app.api.routes.health import router as health_router

# Create the main API router and include all sub-routers
api_router = APIRouter()

# Include routers for different features
api_router.include_router(health_router, tags=["health"])
api_router.include_router(github_router, prefix="/api", tags=["github"])
