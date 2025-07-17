import asyncio
import logging
import os
import time

import requests

from app.core.config import settings
from app.indexing.code_parser import parse_and_extract_chunks
from app.indexing.embedding_generator import get_embedding, get_embedding_model
from app.storage.repo_manager import clone_or_pull_repository
from app.storage.vector_store import (
    CodeChunkSchema,
    create_code_table_if_not_exists,
    drop_table,
    get_lancedb_conn,
)
from app.utils.general_utils import repo_url_to_table_name

logger = logging.getLogger("app")


async def _process_single_file(
    file_path: str, local_repo_path: str, repo_url: str, embedding_model
) -> list[CodeChunkSchema]:
    """Helper function to process a single file asynchronously."""
    relative_file_path = os.path.relpath(file_path, local_repo_path)
    logger.info(f"  - Processing file: {relative_file_path}")
    file_chunks = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = await asyncio.to_thread(f.read)

        # CPU-bound: run in a separate thread
        code_chunks_data = await asyncio.to_thread(
            parse_and_extract_chunks, relative_file_path, content
        )

        for chunk_data in code_chunks_data:
            # CPU-bound: run in a separate thread
            embedding = await asyncio.to_thread(
                get_embedding, chunk_data["code"], embedding_model
            )
            if embedding is not None:
                chunk_schema_item = CodeChunkSchema(
                    id=chunk_data["id"],
                    repo_url=repo_url,
                    file_path=chunk_data["file_path"],
                    code_chunk=chunk_data["code"],
                    embedding=embedding,
                    start_line=chunk_data["start_line"],
                    end_line=chunk_data["end_line"],
                )
                file_chunks.append(chunk_schema_item)
    except Exception as e:
        logger.error(f"    - Error processing file {relative_file_path}: {e}")
    return file_chunks


async def index_repository(repo_url: str):
    """
    Orchestrates the full pipeline of cloning, parsing, embedding, and indexing a repository.

    Args:
        repo_url: The URL of the Git repository to index.
    """
    logger.info(f"--- Starting indexing process for repository: {repo_url} ---")
    start_time = time.time()

    # 1. Load Configuration from Pydantic settings
    repo_clone_dir = settings.REPO_CLONE_DIR
    lancedb_path = settings.LANCEDB_PATH
    embedding_model_name = settings.EMBEDDING_MODEL_NAME

    # Derive a local path for the repo from its URL
    repo_name = "/".join(repo_url.split("/")[-2:]).replace(".git", "")
    table_name = repo_url_to_table_name(repo_url)

    local_repo_path = os.path.join(repo_clone_dir, repo_name)

    # 2. Initialize Services (Embedding Model and DB)
    logger.info("\nStep 1: Initializing services...")
    try:
        embedding_model = get_embedding_model(embedding_model_name)
        db_conn = get_lancedb_conn(lancedb_path)
        # Drop the table to ensure a clean run, making the process idempotent
        drop_table(db_conn, table_name)
        code_table = create_code_table_if_not_exists(db_conn, table_name)

        # Now that we understand the issue, we can remove the debugging code
        # and use an explicit check for None
        if code_table is None:
            logger.error("Error: Failed to create or open LanceDB table. Aborting.")
            return
    except Exception as e:
        logger.error(f"Error during service initialization: {e}. Aborting.")
        return
    logger.info("Services initialized successfully.")

    # 3. Clone or Pull Repository
    logger.info(f"\nStep 2: Cloning/pulling repository into {local_repo_path}...")
    repo = clone_or_pull_repository(repo_url, local_repo_path)
    if not repo:
        logger.error("Error: Failed to clone repository. Aborting.")
        return
    logger.info("Repository ready.")

    # 4. Walk Filesystem, Parse, Embed, and Prepare Data
    logger.info("\nStep 3: Discovering files and preparing for parallel processing...")
    python_files_to_process = []
    for root, _, files in os.walk(local_repo_path):
        if ".git" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                python_files_to_process.append(os.path.join(root, file))

    logger.info(f"Found {len(python_files_to_process)} Python files to process.")
    logger.info("Starting parallel processing of files...")

    tasks = [
        _process_single_file(file_path, local_repo_path, repo_url, embedding_model)
        for file_path in python_files_to_process
    ]

    all_chunks_from_tasks = await asyncio.gather(*tasks)

    all_chunks_to_add = []
    for file_chunk_list in all_chunks_from_tasks:
        all_chunks_to_add.extend(file_chunk_list)
    files_processed = len(python_files_to_process)

    logger.info(
        f"Data preparation complete. Found {len(all_chunks_to_add)} chunks in {files_processed} Python files."
    )

    # 5. Batch Insert into LanceDB
    if all_chunks_to_add:
        logger.info("\nStep 4: Adding data to LanceDB...")
        try:
            # LanceDB's add method can take a list of Pydantic objects directly
            code_table.add(all_chunks_to_add)
            logger.info(
                f"Successfully added {len(all_chunks_to_add)} chunks to the '{table_name}' table."
            )
        except Exception as e:
            logger.error(f"Error adding data to LanceDB: {e}")
    else:
        logger.info("\nStep 4: No new chunks to add to LanceDB.")

    end_time = time.time()
    logger.info(
        f"\n--- Indexing process finished in {end_time - start_time:.2f} seconds. ---"
    )
    logger.info(f"Total rows in table '{table_name}': {len(code_table)}")

    webhook_payload = {
        "event": "indexed",
        "message": "successfully indexed repository",
        "repo_name": repo_name,
        "repo_url": repo_url,
        "table_name": table_name,
        "total_rows": len(code_table),
    }

    # Send webhook notification if URL is configured
    if settings.WEBHOOK_URL:
        try:
            logger.info(f"Sending webhook notification to {settings.WEBHOOK_URL}")
            response = requests.post(
                settings.WEBHOOK_URL,
                json=webhook_payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            logger.info(
                f"Webhook notification sent successfully: {response.status_code}"
            )
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
    else:
        logger.debug("No webhook URL configured, skipping notification")


# Example usage: Run this script directly to index a repository
if __name__ == "__main__":
    # A small, well-known repository is a good example
    # EXAMPLE_REPO_URL = "https://github.com/pallets/flask.git"
    EXAMPLE_REPO_URL = "https://github.com/langchain-ai/langchain.git"
    # EXAMPLE_REPO_URL = "https://github.com/ollama/ollama.git"

    # Setup basic logging for the script execution
    # Note: If running as part of a larger app, logging should be configured centrally.
    # Here, we ensure basic configuration if run standalone.
    from app.core.logging_config import (
        setup_logging,  # Import here to avoid circular dependency if settings are used in logging_config top-level
    )

    setup_logging()  # Initialize logging as defined in core
    logger.info("Running indexer.py directly.")

    # Access settings (Pydantic settings automatically loads .env)
    # We can check for required settings if needed, Pydantic does this on instantiation of Settings()
    # For example, GITHUB_APP_ID and GITHUB_PRIVATE_KEY are mandatory in Settings class.
    # If they are not set in .env or environment, Settings() would raise an error.

    logger.info(f"Using REPO_CLONE_DIR: {settings.REPO_CLONE_DIR}")
    logger.info(f"Using LANCEDB_PATH: {settings.LANCEDB_PATH}")
    logger.info(f"Using EMBEDDING_MODEL_NAME: {settings.EMBEDDING_MODEL_NAME}")

    asyncio.run(index_repository(EXAMPLE_REPO_URL))
