import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from .auth import get_installation_access_token
from .github_client import fetch_pr_diff, post_pr_comment # Import GitHub client functions

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
        if action in ["opened", "reopened", "synchronize", "ready_for_review"]:
            installation_id = payload.get("installation", {}).get("id")
            if not installation_id:
                print("Error: Installation ID not found in payload.")
                # Potentially raise HTTPException or handle error appropriately
                return {"status": "error", "message": "Installation ID missing"}

            try:
                token = get_installation_access_token(installation_id)
                print(
                    f"Successfully obtained installation token for ID: {installation_id}"
                )

                # Extract PR details for fetching diff
                pull_request_payload = payload.get("pull_request", {})
                repository_payload = payload.get("repository", {})

                owner = repository_payload.get("owner", {}).get("login")
                repo_name = repository_payload.get("name")
                pull_number = pull_request_payload.get("number")

                if owner and repo_name and pull_number:
                    print(f"Fetching diff for {owner}/{repo_name} PR #{pull_number}")
                    diff_content = fetch_pr_diff(token, owner, repo_name, pull_number)
                    if diff_content:
                        print(
                            f"Successfully fetched PR diff. Snippet:\n{diff_content[:200]}..."
                        )
                        # In a future ticket, this diff_content will be used for analysis.

                        # Post a placeholder comment
                        placeholder_comment = "AI Reviewer Acknowledged PR."
                        comment_posted = post_pr_comment(token, owner, repo_name, pull_number, placeholder_comment)
                        if comment_posted:
                            print(f"Successfully posted placeholder comment to PR #{pull_number}.")
                        else:
                            print(f"Failed to post placeholder comment to PR #{pull_number}.")
                    else:
                        print("Failed to fetch PR diff.")
                else:
                    print("Error: Missing owner, repo name, or pull number in payload for diff fetching/commenting.")

            except Exception as e:
                print(f"Error in webhook processing: {e}")
                # Handle error appropriately

            print(f"Handling action: {action} for PR #{payload.get('number')}")
            # In a future ticket, we will add code here to trigger a code review.

    else:
        print(f"Received unhandled event: {event}")

    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
