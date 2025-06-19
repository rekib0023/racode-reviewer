import logging
import os
from typing import Dict, List

from app.embedding_generator import get_embedding, initialize_embedding_model
from app.utils import repo_url_to_table_name
from app.vector_store import get_lancedb_conn

# --- Environment & Constants ---
LANCEDB_PATH = os.getenv("LANCEDB_PATH", "./lancedb_data/db")
logger = logging.getLogger("app")


def format_retrieved_chunks(chunks: List[Dict]) -> str:
    """Formats a list of retrieved code chunks into a single string for the prompt."""
    if not chunks:
        return "No relevant code snippets found in the existing codebase."

    formatted_context = "\n--- Relevant Code Snippets from the Codebase ---\n"
    for i, chunk in enumerate(chunks):
        formatted_context += f"\nSnippet {i + 1}: From file `{chunk['file_path']}` (Lines {chunk['start_line']}-{chunk['end_line']})\n"
        formatted_context += f"```python\n{chunk['code_chunk']}\n```\n"
    formatted_context += "--- End of Snippets ---\n"
    return formatted_context


def retrieve_relevant_code_chunks(
    repo_url: str, file_path: str, diff_content: str, limit: int = 5
) -> str:
    """Retrieves relevant code chunks from the vector store for a given file diff."""
    logger.info(f"RAG: Starting retrieval for {file_path} in {repo_url}")
    try:
        db_conn = get_lancedb_conn(LANCEDB_PATH)
        table_name = repo_url_to_table_name(repo_url)

        if table_name not in db_conn.table_names():
            logger.warning(f"RAG: Table '{table_name}' not found. Skipping retrieval.")
            return ""

        table = db_conn.open_table(table_name)
        embedding_model = initialize_embedding_model()

        # Use the diff content as the query
        query_embedding = get_embedding(diff_content, embedding_model)
        if query_embedding is None:
            logger.error("RAG: Failed to generate query embedding. Skipping retrieval.")
            return ""

        # Search for similar chunks, excluding chunks from the same file
        search_results = (
            table.search(query_embedding)
            .where(f"file_path != '{file_path}'")
            .limit(limit)
            .to_list()
        )

        logger.info(f"RAG: Found {len(search_results)} relevant code chunks.")
        return format_retrieved_chunks(search_results)

    except Exception as e:
        logger.error(f"RAG: An error occurred during retrieval: {e}")
        return "Error: Could not retrieve context from the codebase."
