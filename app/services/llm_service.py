import logging
from typing import Any, Dict, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.chat_models import ChatOllama

from app.core.config import get_settings
from app.core.exceptions import LLMServiceException
from app.llm.prompts import CODE_REVIEW_PROMPT_TEMPLATE
from app.llm.rag_retriever import retrieve_relevant_code_chunks
from app.utils.diff_parser import FileDiff

logger = logging.getLogger("app")


# --- AI Model Initialization ---
# Workaround for Pydantic v2 warning in LangChain where a field name
# conflicts with a protected namespace.
class SafeChatOllama(ChatOllama):
    """A ChatOllama subclass that disables Pydantic's protected namespaces."""

    model_config = {"protected_namespaces": ()}


def initialize_llm() -> Optional[SafeChatOllama]:
    """
    Initialize the LLM instance with proper error handling.

    Returns:
        Optional[SafeChatOllama]: Initialized LLM instance or None if initialization fails

    Raises:
        LLMServiceException: If initialization fails due to configuration or connection issues
    """
    settings = get_settings()

    try:
        model = SafeChatOllama(model=settings.CHAT_MODEL_NAME)
        logger.info(
            f"Successfully connected to Ollama model: {settings.CHAT_MODEL_NAME}"
        )
        return model
    except Exception as e:
        error_msg = f"Failed to connect to Ollama. Please ensure Ollama is running. Error: {str(e)}"
        logger.error(error_msg)
        return None


# Initialize the LLM at module import time
llm = initialize_llm()


# --- Review Generation Logic ---
async def generate_review_for_file(
    file_diff: FileDiff, repo_url: str
) -> Dict[str, Any]:
    """
    Generates review comments for a single file diff using RAG.

    Args:
        file_diff: FileDiff object containing the path and content of the file diff
        repo_url: URL of the repository to use for context retrieval

    Returns:
        Dict[str, Any]: A dictionary containing PR summary and inline comments

    Raises:
        LLMServiceException: Captured internally and returned as error message in the review
    """
    if not llm:
        error_msg = "LLM not initialized. Cannot generate review."
        logger.error(error_msg)
        return {
            "pr_summary_comment": "Error: LLM not available. Please check server logs.",
            "inline_comments": [],
        }

    logger.info(f"Generating review for file: {file_diff.path}")

    # Default review response in case of errors
    default_error_response = {
        "pr_summary_comment": f"Error generating review for {file_diff.path}. Please check server logs.",
        "inline_comments": [],
    }

    try:
        # 1. Retrieve context using RAG
        try:
            codebase_context = retrieve_relevant_code_chunks(
                repo_url=repo_url,
                file_path=file_diff.path,
                diff_content=file_diff.content,
            )
            logger.debug(
                f"Successfully retrieved {len(codebase_context)} context chunks for {file_diff.path}"
            )
        except Exception as e:
            error_msg = f"Failed to retrieve context for {file_diff.path}: {str(e)}"
            logger.exception(error_msg)
            raise LLMServiceException("context_retrieval", error_msg) from e

        # 2. Create the LangChain chain
        prompt = ChatPromptTemplate.from_template(CODE_REVIEW_PROMPT_TEMPLATE)
        chain = prompt | llm | JsonOutputParser()

        # 3. Invoke the LLM with the diff and context
        try:
            review_json = await chain.ainvoke(
                {
                    "code_diff": file_diff.content,
                    "codebase_context": codebase_context,
                    "external_context": "Not provided.",
                }
            )
            logger.debug(
                f"Raw LLM response for {file_diff.path}: {str(review_json)[:100]}..."
            )
        except Exception as e:
            error_msg = f"LLM invocation failed for {file_diff.path}: {str(e)}"
            logger.exception(error_msg)
            raise LLMServiceException("llm_invocation", error_msg) from e

        # 4. Validate the response format
        if not review_json or not isinstance(review_json, dict):
            error_msg = f"Invalid response format from LLM for {file_diff.path}"
            logger.warning(error_msg)
            raise LLMServiceException("invalid_response", error_msg)

        # 5. Process and return the review
        inline_comments = review_json.get("inline_comments", [])
        pr_summary = review_json.get("pr_summary_comment", "")

        if not pr_summary and not inline_comments:
            logger.warning(f"Empty review generated for {file_diff.path}")
            return {
                "pr_summary_comment": f"No actionable feedback found for {file_diff.path}.",
                "inline_comments": [],
            }

        num_inline_comments = len(inline_comments)
        logger.info(
            f"Successfully generated review for {file_diff.path} with "
            f"{num_inline_comments} inline comments and "
            f"{len(pr_summary)} chars of summary."
        )
        return review_json

    except LLMServiceException as e:
        # Log but don't re-raise, instead return a user-friendly message
        logger.error(f"LLM service error for {file_diff.path}: {e}")
        return default_error_response
    except Exception as e:
        # Catch any other unexpected exceptions
        logger.exception(
            f"Unexpected error generating review for {file_diff.path}: {e}"
        )
        return default_error_response
