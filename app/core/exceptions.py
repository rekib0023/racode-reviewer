"""
Custom exceptions module.

This module contains custom exceptions for different layers of the application
to improve error handling, reporting, and debugging.
"""


class CodeReviewerException(Exception):
    """Base exception class for all application-specific exceptions."""

    def __init__(
        self,
        message: str = "An error occurred in the Code Reviewer application",
        status_code: int = 500,
    ):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# Repository and Indexing Exceptions
class RepositoryException(CodeReviewerException):
    """Base exception for repository operations."""

    def __init__(
        self, message: str = "Repository operation failed", status_code: int = 500
    ):
        super().__init__(message, status_code)


class RepositoryCloneError(RepositoryException):
    """Raised when repository cloning fails."""

    def __init__(self, repo_url: str, reason: str):
        message = f"Failed to clone repository {repo_url}: {reason}"
        super().__init__(message, status_code=500)


class RepositoryIndexingError(RepositoryException):
    """Raised when repository indexing fails."""

    def __init__(self, repo_url: str, reason: str):
        message = f"Failed to index repository {repo_url}: {reason}"
        super().__init__(message, status_code=500)


# GitHub Service Exceptions
class GitHubServiceException(CodeReviewerException):
    """Base exception for GitHub service operations."""

    def __init__(
        self, message: str = "GitHub service operation failed", status_code: int = 500
    ):
        super().__init__(message, status_code)


class InvalidWebhookPayloadError(GitHubServiceException):
    """Raised when a webhook payload is invalid or missing required fields."""

    def __init__(self, details: str):
        message = f"Invalid webhook payload: {details}"
        super().__init__(message, status_code=400)


class WebhookProcessingError(GitHubServiceException):
    """Raised when processing a webhook event fails."""

    def __init__(self, event_type: str, reason: str):
        message = f"Failed to process {event_type} webhook event: {reason}"
        super().__init__(message, status_code=500)


# LLM Service Exceptions
class LLMServiceException(CodeReviewerException):
    """Base exception for LLM service operations."""

    def __init__(
        self, message: str = "LLM service operation failed", status_code: int = 500
    ):
        super().__init__(message, status_code)


class ReviewGenerationError(LLMServiceException):
    """Raised when generating a code review fails."""

    def __init__(self, file_path: str, reason: str):
        message = f"Failed to generate review for file {file_path}: {reason}"
        super().__init__(message, status_code=500)


# Notification Exceptions
class WebhookNotificationError(CodeReviewerException):
    """Raised when sending a webhook notification fails."""

    def __init__(self, webhook_url: str, reason: str):
        message = f"Failed to send webhook notification to {webhook_url}: {reason}"
        super().__init__(message, status_code=500)


# Database Exceptions
class VectorDBError(CodeReviewerException):
    """Raised when a vector database operation fails."""

    def __init__(self, operation: str, reason: str):
        message = f"Vector database {operation} operation failed: {reason}"
        super().__init__(message, status_code=500)
