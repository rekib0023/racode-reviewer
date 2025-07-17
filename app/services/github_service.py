"""GitHub service module.

This module contains services for handling GitHub webhook events, including
repository installation, push events, and pull request review events.
"""

import asyncio
from typing import Any, Dict, List, Tuple

import requests
from requests.exceptions import RequestException

from app.core.config import get_settings
from app.core.exceptions import (
    InvalidWebhookPayloadError,
    RepositoryIndexingError,
    WebhookProcessingError,
)
from app.core.logging_config import get_logger
from app.indexing.incremental_indexer import incremental_index_repository
from app.indexing.indexer import index_repository
from app.services.llm_service import generate_review_for_file
from app.utils.diff_parser import parse_diff

# Get logger for this module
logger = get_logger(__name__)


async def process_installation_event(full_name: str) -> None:
    """
    Process an installation event by triggering the indexing pipeline.

    Args:
        full_name: Full name of the GitHub repository (owner/repo)

    Raises:
        RepositoryIndexingError: If indexing the repository fails
    """
    repo_url = f"https://github.com/{full_name}.git"

    logger.info(f"Processing installation event for repo: {full_name}")

    try:
        await index_repository(repo_url)
        logger.info(f"Successfully indexed repository: {full_name}")

        # Send webhook notification if configured
        settings = get_settings()
        if settings.WEBHOOK_URL:
            try:
                logger.info(
                    f"Sending installation success notification to {settings.WEBHOOK_URL}"
                )
                webhook_payload = {
                    "event": "installation",
                    "message": "successfully indexed repository",
                    "repository": full_name,
                }

                response = requests.post(
                    settings.WEBHOOK_URL,
                    json=webhook_payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                logger.info(
                    f"Installation notification sent successfully: {response.status_code}"
                )
            except RequestException as e:
                logger.warning(f"Failed to send installation notification: {str(e)}")
                # Don't raise here, as the main operation succeeded
    except Exception as e:
        error_message = f"Failed to process installation for {full_name}: {str(e)}"
        logger.exception(error_message)
        raise RepositoryIndexingError(repo_url, str(e)) from e


async def process_push_event(push_info: Dict[str, Any]) -> None:
    """
    Process a push event by triggering the incremental indexing pipeline.

    Args:
        push_info: Dictionary containing push event information including:
                  repo_name, repo_url, before_commit, after_commit

    Raises:
        InvalidWebhookPayloadError: If required fields are missing from push_info
        RepositoryIndexingError: If indexing the repository fails
    """
    # Validate required fields
    required_fields = ["repo_name", "repo_url", "before_commit", "after_commit"]
    for field in required_fields:
        if field not in push_info:
            error_msg = f"Missing required field '{field}' in push event payload"
            logger.error(error_msg)
            raise InvalidWebhookPayloadError(error_msg)

    logger.info(f"Processing push event for repository: {push_info['repo_name']}")

    try:
        # Perform the incremental indexing
        incremental_index_repository(
            push_info["repo_url"], push_info["before_commit"], push_info["after_commit"]
        )
        logger.info(
            f"Successfully processed push event for {push_info['repo_name']} "
            f"(commits {push_info['before_commit'][:7]} → {push_info['after_commit'][:7]})"
        )
    except Exception as e:
        error_msg = (
            f"Failed to process push event for {push_info['repo_name']}: {str(e)}"
        )
        logger.exception(error_msg)
        raise RepositoryIndexingError(push_info["repo_url"], str(e)) from e


async def handle_pull_request_event(
    payload: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Handles the full pipeline for a pull request event:
    - Fetches the diff
    - For each file, retrieves RAG context and generates AI review
    - Posts all comments in a single review to GitHub

    Args:
        payload: Dictionary containing pull request event data

    Returns:
        Tuple[str, List[Dict]]: PR summary text and list of inline comments

    Raises:
        InvalidWebhookPayloadError: If required fields are missing from payload
        WebhookProcessingError: If processing the PR event fails
    """
    settings = get_settings()

    try:
        # Validate required fields
        repo_url = payload.get("clone_url")
        diff_content = payload.get("diff_content")

        if not repo_url or not diff_content:
            error_msg = "Missing required fields in pull request payload: 'clone_url' or 'diff_content'"
            logger.error(error_msg)
            raise InvalidWebhookPayloadError(error_msg)

        # Parse the diff content
        try:
            file_diffs = parse_diff(diff_content)
            logger.info(f"Parsed diff into {len(file_diffs)} file(s).")
        except Exception as e:
            error_msg = f"Failed to parse diff content: {str(e)}"
            logger.exception(error_msg)
            raise WebhookProcessingError("parse_diff", error_msg) from e

        # Prepare for review generation
        all_inline_comments = []
        all_pr_summary_parts = []
        review_tasks = []

        # Create tasks for parallel processing
        for file_diff in file_diffs:
            task = generate_review_for_file(file_diff, repo_url)
            review_tasks.append(task)

        # Run all file review tasks concurrently
        logger.info(f"Starting parallel review for {len(review_tasks)} files...")
        try:
            results_from_tasks = await asyncio.gather(
                *review_tasks, return_exceptions=True
            )
            logger.info(f"Completed parallel review for {len(review_tasks)} files.")
        except Exception as e:
            error_msg = f"Failed during parallel review execution: {str(e)}"
            logger.exception(error_msg)
            raise WebhookProcessingError("review_execution", error_msg) from e

        # Process the results from asyncio.gather
        for i, result in enumerate(results_from_tasks):
            if i >= len(file_diffs):
                logger.warning(
                    f"Result index {i} out of range for file_diffs (length {len(file_diffs)})"
                )
                continue

            file_diff = file_diffs[i]  # Get the corresponding file_diff
            if isinstance(result, Exception):
                logger.error(
                    f"Error generating review for file {file_diff.path}: {result}"
                )
                continue  # Skip this file if an error occurred

            # Process file review result
            file_pr_summary = result.get("pr_summary_comment", "")
            if file_pr_summary:
                all_pr_summary_parts.append(
                    f"**Summary for `{file_diff.path}`:**\n{file_pr_summary}"
                )

            # Process inline comments
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
                        f"Could not map line {line_number} for {file_diff.path}. "
                        "Comment will be skipped or comment text missing."
                    )

        # Prepare the final PR summary
        final_pr_summary = "\n\n---\n\n".join(all_pr_summary_parts)
        if not final_pr_summary and not all_inline_comments:
            logger.info(
                "No actionable comments or summary generated. No review will be posted."
            )
            return "", []

        if not final_pr_summary:
            final_pr_summary = "Review complete. Please see inline comments."
        elif not all_inline_comments:
            logger.info("No inline comments, but a PR summary was generated.")

        # Send webhook notification if configured
        if settings.WEBHOOK_URL:
            try:
                logger.info(f"Sending webhook notification to {settings.WEBHOOK_URL}")
                webhook_payload = {
                    "event": "review",
                    "message": "successfully indexed repository",
                    "pr_summary": final_pr_summary,
                    "inline_comments": all_inline_comments,
                }

                response = requests.post(
                    settings.WEBHOOK_URL,
                    json=webhook_payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()  # Raise exception for 4XX/5XX responses
                logger.info(
                    f"Webhook notification sent successfully: {response.status_code}"
                )
            except RequestException as e:
                error_msg = f"Failed to send webhook notification: {str(e)}"
                logger.warning(error_msg)
                # Don't raise here, as we still want to return the review results

        return final_pr_summary, all_inline_comments

    except InvalidWebhookPayloadError:
        # Re-raise without wrapping to preserve the original exception
        raise
    except WebhookProcessingError:
        # Re-raise without wrapping to preserve the original exception
        raise
    except Exception as e:
        error_msg = f"Unexpected error processing pull request event: {str(e)}"
        logger.exception(error_msg)
        raise WebhookProcessingError("unexpected", error_msg) from e
