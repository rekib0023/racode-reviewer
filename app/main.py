import json
import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from app.core.logging_config import setup_logging
from app.services.github_service import (
    handle_pull_request_event,
    process_installation_event,
    process_push_event,
)

# Initialize logging
setup_logging()
logger = logging.getLogger("app")

# --- FastAPI App Initialization ---
app = FastAPI(title="Code Reviewer API")


# --- API Endpoints ---
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "message": "Code Reviewer API is running."}


@app.post("/api/reviewer")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives and processes webhook events from GitHub."""
    payload_body = await request.body()
    payload = json.loads(payload_body)
    event = payload.get("event")

    logger.info(f"Received webhook event: {event}")

    match event:
        case "installation":
            installation_id = payload.get("installation_id")
            if not installation_id:
                raise HTTPException(status_code=400, detail="Installation ID missing")
            repositories = payload.get("repositories", [])
            for repo in repositories:
                background_tasks.add_task(process_installation_event, repo)
            return {
                "status": "accepted",
                "message": "Installation event accepted for processing.",
            }
        case "push":
            # push_info = extract_push_event_info(payload)
            # if not push_info:
            #     raise HTTPException(
            #         status_code=400, detail="Invalid push event payload"
            #     )
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
            return {"status": "ignored", "message": f"Event '{event}' not processed."}


if __name__ == "__main__":
    import uvicorn

    print("Starting Code Reviewer API server...")
    print("Webhook endpoint available at: /api/reviewer")
    print("Health check endpoint available at: /health")
    uvicorn.run(app, host="0.0.0.0", port=8000)
