"""
Main FastAPI application module.

This module initializes the FastAPI application and includes route definitions.
The application is structured using FastAPI best practices including:
- API Routers for route organization
- Dependency Injection for service dependencies
- Pydantic models for request/response validation
- Proper exception handling and logging
"""

import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import get_settings
from app.api.routes import api_router
from app.core.config import Settings
from app.core.logging_config import get_logger, setup_logging

# Initialize logging
setup_logging()
logger = get_logger(__name__)


def create_application(settings: Settings = Depends(get_settings)) -> FastAPI:
    """
    Factory function to create and configure the FastAPI application.

    Args:
        settings: Application settings from dependency injection

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    application = FastAPI(
        title="Code Reviewer API",
        description="API for code review automation with RAG and LLM capabilities",
        version="1.0.0",
    )

    # Add CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure this appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router with all routes
    application.include_router(api_router)

    @application.on_event("startup")
    async def startup_event():
        logger.info("Starting Code Reviewer API")

    @application.on_event("shutdown")
    async def shutdown_event():
        logger.info("Shutting down Code Reviewer API")

    return application


# Create the FastAPI application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Code Reviewer API server in development mode")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload for development
        log_level="info",
    )
