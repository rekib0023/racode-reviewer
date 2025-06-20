import asyncio
import logging
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.github.auth import get_installation_access_token
from app.github.client import fetch_pr_diff, post_review
from app.indexing.incremental_indexer import incremental_index_repository
from app.indexing.indexer import index_repository
from app.services.llm_service import generate_review_for_file
from app.utils.diff_parser import parse_diff

logger = logging.getLogger("app")


async def process_installation_event(full_name: str):
    """Process an installation event by triggering the incremental indexing pipeline."""
    logger.info(f"Processing installation event for repo: {full_name}")
    await index_repository(f"https://github.com/{full_name}.git")


async def check_github_app_installation(token: str) -> bool:
    """Checks if the GitHub App is installed for the user authenticated with the given token."""
    if not settings.GITHUB_APP_NAME:
        logger.error("GITHUB_APP_NAME environment variable is not set.")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = "https://api.github.com/user/installations"

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, headers=headers)
            res.raise_for_status()
            data = res.json()
            installations = data.get("installations", [])
            for inst in installations:
                if inst.get("app_slug") == settings.GITHUB_APP_NAME:
                    logger.info(
                        f"App '{settings.GITHUB_APP_NAME}' is installed for the user."
                    )
                    return True
            logger.info(
                f"App '{settings.GITHUB_APP_NAME}' is not installed for the user."
            )
            return False
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error while checking installations: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"An error occurred while checking installations: {e}")
            return False


async def process_push_event(push_info: Dict[str, str]):
    """Process a push event by triggering the incremental indexing pipeline."""
    logger.info(f"Processing push event for repository: {push_info['repo_name']}")
    incremental_index_repository(
        push_info["repo_url"], push_info["before_commit"], push_info["after_commit"]
    )


async def handle_pull_request_event(payload: Dict[str, Any]):
    """
    Handles the full pipeline for a pull request event:
    - Fetches the diff
    - For each file, retrieves RAG context and generates AI review
    - Posts all comments in a single review to GitHub
    """
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        logger.error("Error: Installation ID missing.")
        return

    try:
        token = get_installation_access_token(installation_id)
        pull_request = payload.get("pull_request", {})
        repo_info = payload.get("repository", {})
        owner = repo_info.get("owner", {}).get("login")
        repo_name = repo_info.get("name")
        repo_url = repo_info.get("clone_url")
        pull_number = pull_request.get("number")

        if not all([owner, repo_name, repo_url, pull_number]):
            logger.error("Error: Missing PR details in payload.")
            return

        diff_content = fetch_pr_diff(token, owner, repo_name, pull_number)
        if not diff_content:
            logger.error(f"Failed to fetch diff for PR #{pull_number}.")
            return

        logger.info(f"Successfully fetched diff for PR #{pull_number}. Parsing diff...")
        file_diffs = parse_diff(diff_content)
        logger.info(f"Parsed diff into {len(file_diffs)} file(s).")

        all_inline_comments = []
        all_pr_summary_parts = []
        review_tasks = []

        for file_diff in file_diffs:
            # Create a task for each file review
            task = generate_review_for_file(file_diff, repo_url)
            review_tasks.append(task)

        # Run all file review tasks concurrently
        logger.info(f"Starting parallel review for {len(review_tasks)} files...")
        results_from_tasks = await asyncio.gather(*review_tasks, return_exceptions=True)
        logger.info(f"Completed parallel review for {len(review_tasks)} files.")

        # Process the results from asyncio.gather
        for i, result in enumerate(results_from_tasks):
            file_diff = file_diffs[i]  # Get the corresponding file_diff
            if isinstance(result, Exception):
                logger.error(
                    f"Error generating review for file {file_diff.path}: {result}"
                )
                continue  # Skip this file if an error occurred

            # result is the dict {"pr_summary_comment": "...", "inline_comments": [...]} for this file
            file_pr_summary = result.get("pr_summary_comment", "")
            if file_pr_summary:
                all_pr_summary_parts.append(
                    f"**Summary for `{file_diff.path}`:**\n{file_pr_summary}"
                )

            inline_comments_for_file = result.get("inline_comments", [])
            for comment in inline_comments_for_file:
                line_number = comment.get("line_number")
                comment_text = comment.get("comment")

                # Map the line number to its position in the diff
                position = file_diff.line_mapping.get(line_number)

                if position and comment_text:
                    all_inline_comments.append(
                        {
                            "path": file_diff.path,
                            "body": comment_text,
                            "position": position,
                        }
                    )
                else:
                    logger.warning(
                        f"Warning: Could not map line {line_number} for {file_diff.path}. Comment will be skipped or comment text missing."
                    )

        final_pr_summary = "\n\n---\n\n".join(all_pr_summary_parts)
        if not final_pr_summary and not all_inline_comments:
            logger.info(
                "No actionable comments or summary generated. No review will be posted."
            )
            return

        if not final_pr_summary:
            final_pr_summary = "Review complete. Please see inline comments."
        elif not all_inline_comments:
            # If there's a summary but no inline comments, we might still want to post the summary.
            logger.info("No inline comments, but a PR summary was generated.")

        logger.info(
            f"Submitting a review with a PR summary and {len(all_inline_comments)} inline comments."
        )
        post_review(
            token, owner, repo_name, pull_number, final_pr_summary, all_inline_comments
        )

    except Exception as e:
        logger.error(f"An error occurred in the webhook handler: {e}")
