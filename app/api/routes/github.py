"""
GitHub webhook endpoints and handlers.

This module contains routes for handling GitHub webhook events, including
installation events, push events, and pull request review events.
"""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger
from app.services.github_service import (
    handle_pull_request_event,
    process_installation_event,
    process_push_event,
)

router = APIRouter()
logger = get_logger(__name__)


@router.post("/reviewer")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    """
    Receives and processes webhook events from GitHub.

    This endpoint handles different types of GitHub events and delegates processing
    to appropriate background tasks.

    Args:
        request: The incoming HTTP request
        background_tasks: FastAPI background tasks manager
        settings: Application settings

    Returns:
        Dict[str, str]: Status response with message

    Raises:
        HTTPException: If request payload is invalid or missing required data
    """
    try:
        payload_body = await request.body()
        payload = json.loads(payload_body)
        event = payload.get("event")

        if not event:
            raise HTTPException(status_code=400, detail="Event type missing in payload")

        logger.info(f"Received webhook event: {event}", extra={"event_type": event})

        match event:
            case "installation":
                installation_id = payload.get("installation_id")
                if not installation_id:
                    raise HTTPException(
                        status_code=400, detail="Installation ID missing"
                    )

                repositories = payload.get("repositories", [])
                for repo in repositories:
                    background_tasks.add_task(process_installation_event, repo)

                return {
                    "status": "accepted",
                    "message": f"Installation event accepted for processing {len(repositories)} repositories.",
                }

            case "push":
                background_tasks.add_task(process_push_event, payload)
                return {
                    "status": "accepted",
                    "message": "Push event accepted for indexing.",
                }

            case "review":
                background_tasks.add_task(handle_pull_request_event, payload)
                return {
                    "status": "accepted",
                    "message": "PR event accepted for review.",
                }

            case _:
                logger.warning(f"Unhandled event type: {event}")
                return {
                    "status": "ignored",
                    "message": f"Event '{event}' not processed.",
                }

    except json.JSONDecodeError:
        logger.error("Failed to parse webhook payload as JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.exception(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
