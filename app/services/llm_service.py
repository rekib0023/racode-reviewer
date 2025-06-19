import logging
from typing import Any, Dict

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.chat_models import ChatOllama

from app.core.config import settings
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


llm = None
try:
    llm = SafeChatOllama(model=settings.CHAT_MODEL_NAME)
    logger.info("Successfully connected to Ollama model in llm_service.")
except Exception as e:
    logger.error(
        f"Failed to connect to Ollama in llm_service. Please ensure Ollama is running. Error: {e}"
    )


# --- Review Generation Logic ---
async def generate_review_for_file(
    file_diff: FileDiff, repo_url: str
) -> Dict[str, Any]:
    """Generates review comments for a single file diff using RAG."""
    if not llm:
        logger.error("LLM not initialized. Cannot generate review.")
        return {
            "pr_summary_comment": "Error: LLM not available.",
            "inline_comments": [],
        }

    logger.info(f"Generating review for file: {file_diff.path}")
    try:
        # 1. Retrieve context using RAG
        codebase_context = retrieve_relevant_code_chunks(
            repo_url=repo_url, file_path=file_diff.path, diff_content=file_diff.content
        )

        # 2. Create the LangChain chain (can be initialized once if preferred)
        prompt = ChatPromptTemplate.from_template(CODE_REVIEW_PROMPT_TEMPLATE)
        chain = prompt | llm | JsonOutputParser()

        # 3. Invoke the LLM with the diff and context
        review_json = await chain.ainvoke(
            {
                "code_diff": file_diff.content,
                "codebase_context": codebase_context,
                "external_context": "Not provided.",  # Or pass actual external context if available
            }
        )

        if (
            review_json
            and isinstance(review_json, dict)
            and "inline_comments" in review_json
        ):
            num_inline_comments = len(review_json.get("inline_comments", []))
            logger.info(
                f"Received {num_inline_comments} inline comments and a PR summary for {file_diff.path}."
            )
            return review_json
        else:
            logger.warning(
                f"No valid review (or unexpected format) generated for {file_diff.path}. Defaulting."
            )
            return {
                "pr_summary_comment": f"No specific feedback generated for {file_diff.path}.",
                "inline_comments": [],
            }

    except Exception as e:
        logger.error(f"Error generating review for {file_diff.path}: {e}")
        return {
            "pr_summary_comment": f"Error generating review for {file_diff.path}.",
            "inline_comments": [],
        }
