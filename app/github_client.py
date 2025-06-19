import requests

GITHUB_API_BASE_URL = "https://api.github.com"


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
            print(
                f"Error fetching PR diff: Forbidden. Check token permissions. Details: {e.response.text}"
            )
        elif e.response.status_code == 404:
            print(
                f"Error fetching PR diff: Not Found. Check owner, repo, or pull number. Details: {e.response.text}"
            )
        else:
            print(f"Error fetching PR diff: {e}. Details: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching PR diff: {e}")
        return None


def post_pr_comment(
    installation_token: str, owner: str, repo: str, issue_number: int, body: str
) -> bool:
    """Posts a comment to a given pull request (issue)."""
    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    payload = {"body": body}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raises an exception for 4XX/5XX errors
        print(f"Successfully posted comment to PR #{issue_number} in {owner}/{repo}.")
        return True
    except requests.exceptions.HTTPError as e:
        print(
            f"Error posting comment to PR #{issue_number} in {owner}/{repo}: {e}. Details: {e.response.text}"
        )
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error posting comment to PR #{issue_number} in {owner}/{repo}: {e}")
        return False
