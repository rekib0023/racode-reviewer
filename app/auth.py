import os
import time

import jwt
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY")

# Simple in-memory cache for installation tokens
# {installation_id: {"token": "xyz", "expires_at": 1234567890}}
_installation_token_cache = {}


def create_jwt(app_id, private_key):
    """Creates a JWT for GitHub App authentication."""
    now = int(time.time())
    payload = {
        "iat": now,  # Issued at time
        "exp": now + (10 * 60),  # JWT expiration time (10 minutes maximum)
        "iss": app_id,  # Issuer (your app's ID)
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_access_token(installation_id):
    """Gets an installation access token for a given installation ID."""
    if not GITHUB_APP_ID or not GITHUB_PRIVATE_KEY:
        raise ValueError("GitHub App ID or Private Key not configured.")

    # Check cache first
    cached_token_info = _installation_token_cache.get(installation_id)
    if cached_token_info and cached_token_info["expires_at"] > time.time() + 60: # Add a 60-second buffer
        print(f"Using cached installation token for installation ID: {installation_id}")
        return cached_token_info["token"]

    app_jwt = create_jwt(GITHUB_APP_ID, GITHUB_PRIVATE_KEY)

    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"

    response = requests.post(url, headers=headers)
    response.raise_for_status()  # Raise an exception for HTTP errors

    token_data = response.json()
    token = token_data["token"]
    expires_at_str = token_data["expires_at"]  # Format: 2016-07-14T17:09:27Z

    # Convert expires_at string to Unix timestamp using datetime.fromisoformat
    if expires_at_str.endswith('Z'):
        expires_at_str = expires_at_str[:-1] + '+00:00'  # fromisoformat expects +HH:MM for timezone
    
    from datetime import datetime
    expires_at_dt_obj = datetime.fromisoformat(expires_at_str)
    expires_at_timestamp = int(expires_at_dt_obj.timestamp())

    # Store in cache
    _installation_token_cache[installation_id] = {
        "token": token,
        "expires_at": expires_at_timestamp
    }
    print(f"Fetched new installation token for installation ID: {installation_id}")
    return token
