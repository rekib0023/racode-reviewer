import os
# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException

from app.common.webhook_utils import parse_webhook_payload, extract_push_event_info
from app.incremental_indexer import incremental_index_repository
from .auth import get_installation_access_token
from .github_client import fetch_pr_diff, post_pr_comment

load_dotenv()

app = FastAPI(title="Code Reviewer API")


@app.get("/health")
def health_check():
    """
    Health check endpoint to confirm the service is running.
    """
    return {"status": "ok"}


async def process_push_event(push_info: Dict[str, str]) -> Dict[str, Any]:
    """
    Process a push event by triggering the incremental indexing pipeline.

    Args:
        push_info: Dictionary containing repository URL, before commit, and after commit.

    Returns:
        The result of the incremental indexing process.
    """
    print(f"Processing push event for repository: {push_info['repo_name']}")
    print(f"Changes from {push_info['before_commit']} to {push_info['after_commit']}")

    # Call the incremental indexing function
    result = incremental_index_repository(
        push_info["repo_url"], push_info["before_commit"], push_info["after_commit"]
    )

    return result


@app.post("/api/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives webhook events from GitHub.
    
    This unified endpoint handles both push events (for code indexing) and
    pull request events (for code review).
    """
    # Parse and validate the webhook payload
    payload = await parse_webhook_payload(request)
    
    # Get the event type from the headers
    event = request.headers.get("X-GitHub-Event")

    # Handle push events for code indexing
    if event == "push":
        # Extract push event information
        push_info = extract_push_event_info(payload)
        if not push_info:
            raise HTTPException(status_code=400, detail="Invalid push event payload")

        # Process the push event in the background
        background_tasks.add_task(process_push_event, push_info)

        return {
            "status": "accepted",
            "message": f"Push event for {push_info['repo_name']} accepted for processing",
            "repository": push_info["repo_name"],
            "before": push_info["before_commit"],
            "after": push_info["after_commit"],
        }
    
    # Handle pull request events for code review
    elif event == "pull_request":
        action = payload.get("action")
        print(f"Received pull_request event with action: {action}")

        # Handle specific pull request actions
        if action in ["opened", "reopened", "synchronize", "ready_for_review"]:
            installation_id = payload.get("installation", {}).get("id")
            if not installation_id:
                print("Error: Installation ID not found in payload.")
                return {"status": "error", "message": "Installation ID missing"}

            try:
                token = get_installation_access_token(installation_id)
                print(f"Successfully obtained installation token for ID: {installation_id}")

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
                        print(f"Successfully fetched PR diff. Snippet:\n{diff_content[:200]}...")
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

                return {"status": "success", "message": f"Processed PR #{pull_number} with action {action}"}
                
            except Exception as e:
                print(f"Error in webhook processing: {e}")
                return {"status": "error", "message": str(e)}
        else:
            # Ignore other pull request actions
            return {"status": "ignored", "message": f"Pull request action '{action}' is not processed"}
    
    # Handle other event types
    else:
        return {
            "status": "ignored",
            "message": f"Event type '{event}' is not processed",
        }


if __name__ == "__main__":
    import uvicorn
    
    print("Starting Code Reviewer API server...")
    print("Webhook endpoint available at: /api/webhook")
    print("Health check endpoint available at: /health")
    uvicorn.run(app, host="0.0.0.0", port=8000)
