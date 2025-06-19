import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv()

APP_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

app = FastAPI()


@app.get("/health")
def health_check():
    """
    Health check endpoint to confirm the service is running.
    """
    return {"status": "ok"}


@app.post("/api/webhook")
async def github_webhook(request: Request):
    """
    Receives webhook events from GitHub.
    """
    # Verify the webhook signature
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(
            status_code=400, detail="X-Hub-Signature-256 header is missing!"
        )

    body = await request.body()
    expected_signature = (
        "sha256="
        + hmac.new(APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=400, detail="Request signature does not match!")

    # Process the webhook payload
    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()

    if event == "pull_request":
        action = payload.get("action")
        print(f"Received pull_request event with action: {action}")

        # Handle specific pull request actions
        if action in ["opened", "synchronize", "ready_for_review"]:
            # Add your bot's logic here for these events
            print(f"Handling action: {action} for PR #{payload.get('number')}")
            # In a future ticket, we will add code here to trigger a code review.

    else:
        print(f"Received unhandled event: {event}")

    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
