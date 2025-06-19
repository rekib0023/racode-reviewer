import logging

import requests

GITHUB_API_BASE_URL = "https://api.github.com"
logger = logging.getLogger("app")


def fetch_pr_diff(
    installation_token: str, owner: str, repo: str, pull_number: int
) -> str | None:
    """Fetches the diff content for a given pull request."""
    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github.v3.diff",  # Request diff format
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raises an exception for 4XX/5XX errors
        return response.text  # The diff content
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            logger.error(
                f"Error fetching PR diff: Forbidden. Check token permissions. Details: {e.response.text}"
            )
        elif e.response.status_code == 404:
            logger.error(
                f"Error fetching PR diff: Not Found. Check owner, repo, or pull number. Details: {e.response.text}"
            )
        else:
            logger.error(f"Error fetching PR diff: {e}. Details: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching PR diff: {e}")
        return None


def post_pr_comment(
    installation_token: str, owner: str, repo: str, issue_number: int, body: str
) -> bool:
    """Posts a general comment to a given pull request (issue)."""
    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    payload = {"body": body}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"Successfully posted general comment to PR #{issue_number}.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error posting general comment to PR #{issue_number}: {e}")
        return False


def post_review(
    installation_token: str, owner: str, repo: str, pull_number: int, comments: list
) -> bool:
    """Posts a formal review with line-specific comments to a pull request."""
    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"

    # If there are no comments, we can post a general approval or do nothing.
    # For now, we will only post if there are comments.
    if not comments:
        logger.info("No comments to post, skipping review submission.")
        return True

    payload = {
        "body": "AI code review complete. See comments below.",
        "event": "COMMENT",
        "comments": comments,  # A list of comment objects
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(
            f"Successfully posted review with {len(comments)} comments to PR #{pull_number}."
        )
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Error posting review to PR #{pull_number}: {e}. Details: {e.response.text}"
        )
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error posting review to PR #{pull_number}: {e}")
        return False
