import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from app.core.logging_config import setup_logging
from app.github.webhook_utils import extract_push_event_info, parse_webhook_payload
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


@app.post("/api/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives and processes webhook events from GitHub."""
    payload = await parse_webhook_payload(request)
    event = request.headers.get("X-GitHub-Event")

    match event:
        case "installation":
            installation_id = payload.get("installation", {}).get("id")
            if not installation_id:
                raise HTTPException(status_code=400, detail="Installation ID missing")
            repositories = payload.get("repositories", [])
            for repo in repositories:
                background_tasks.add_task(process_installation_event, repo["full_name"])
            return {
                "status": "accepted",
                "message": "Installation event accepted for processing.",
            }
        case "push":
            push_info = extract_push_event_info(payload)
            if not push_info:
                raise HTTPException(
                    status_code=400, detail="Invalid push event payload"
                )
            background_tasks.add_task(process_push_event, push_info)
            return {
                "status": "accepted",
                "message": "Push event accepted for indexing.",
            }

        case "pull_request":
            action = payload.get("action")
            if action in ["opened", "reopened", "synchronize"]:
                background_tasks.add_task(handle_pull_request_event, payload)
                return {
                    "status": "accepted",
                    "message": f"PR event '{action}' accepted for review.",
                }
            return {
                "status": "ignored",
                "message": f"PR action '{action}' not processed.",
            }

        case _:
            return {"status": "ignored", "message": f"Event '{event}' not processed."}


if __name__ == "__main__":
    import uvicorn

    print("Starting Code Reviewer API server...")
    print("Webhook endpoint available at: /api/webhook")
    print("Health check endpoint available at: /health")
    uvicorn.run(app, host="0.0.0.0", port=8000)
