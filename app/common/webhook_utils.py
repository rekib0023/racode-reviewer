import hashlib
import hmac
import json
import os
from typing import Dict, Any, Optional

from fastapi import HTTPException, Request
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get GitHub webhook secret from environment variables
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
if not GITHUB_WEBHOOK_SECRET:
    print(
        "Warning: GITHUB_WEBHOOK_SECRET not set. Webhook signature validation will be skipped."
    )


async def verify_webhook_signature(request: Request) -> bytes:
    """
    Verify that the webhook request came from GitHub by validating the signature.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        The raw request body bytes if signature is valid
        
    Raises:
        HTTPException: If the signature is invalid or missing
    """
    # Get the signature from the headers
    signature_header = request.headers.get("X-Hub-Signature-256")
    
    if not signature_header:
        raise HTTPException(
            status_code=400, detail="X-Hub-Signature-256 header is missing!"
        )
    
    # Read the raw request body
    payload_body = await request.body()
    
    # Skip validation if no secret is configured (for development only)
    if not GITHUB_WEBHOOK_SECRET:
        return payload_body
    
    # The signature header starts with "sha256="
    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=400, detail="Invalid signature format!")
    
    # Get the signature from the header
    signature = signature_header[7:]  # Remove "sha256=" prefix
    
    # Calculate the expected signature
    expected_signature = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    
    # Compare signatures using a constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    return payload_body


def extract_push_event_info(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Extract relevant information from a GitHub push event payload.
    
    Args:
        payload: The parsed JSON payload from the webhook.
        
    Returns:
        A dictionary containing repository URL, before commit, and after commit,
        or None if the required information is not available.
    """
    try:
        # Extract repository URL
        repo_url = payload.get("repository", {}).get("clone_url")
        if not repo_url:
            print("Error: Repository URL not found in payload")
            return None
        
        # Extract before and after commit SHAs
        before_commit = payload.get("before")
        after_commit = payload.get("after")
        
        if not before_commit or not after_commit:
            print("Error: Before or after commit SHA not found in payload")
            return None
        
        # Extract repository name for logging
        repo_name = payload.get("repository", {}).get("name", "unknown")
        
        return {
            "repo_url": repo_url,
            "before_commit": before_commit,
            "after_commit": after_commit,
            "repo_name": repo_name,
        }
    except Exception as e:
        print(f"Error extracting push event info: {e}")
        return None


async def parse_webhook_payload(request: Request) -> Dict[str, Any]:
    """
    Parse and validate the webhook payload.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        The parsed JSON payload
        
    Raises:
        HTTPException: If the payload is invalid JSON
    """
    payload_body = await verify_webhook_signature(request)
    
    # Parse the JSON payload
    try:
        payload = json.loads(payload_body)
        return payload
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
