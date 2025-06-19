import logging
import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import time
from typing import Dict, List

from git import GitCommandError, Repo

from app.core.config import settings
from app.indexing.code_parser import parse_and_extract_chunks
from app.indexing.embedding_generator import get_embedding, initialize_embedding_model
from app.storage.repo_manager import clone_or_pull_repository
from app.storage.vector_store import (
    CodeChunkSchema,
    create_code_table_if_not_exists,
    get_lancedb_conn,
)
from app.utils.general_utils import repo_url_to_table_name

logger = logging.getLogger("app")


def get_changed_files(
    repo: Repo, old_commit: str, new_commit: str
) -> Dict[str, List[str]]:
    """
    Identifies files that were added, modified, or deleted between two commits.

    Args:
        repo: The GitPython Repo object.
        old_commit: The SHA or reference of the old commit.
        new_commit: The SHA or reference of the new commit.

    Returns:
        A dictionary with keys 'added', 'modified', and 'deleted', each containing
        a list of file paths relative to the repository root.
    """
    try:
        # Get the diff between the two commits
        diff_index = repo.git.diff("--name-status", old_commit, new_commit)

        # Parse the diff output
        added_files = []
        modified_files = []
        deleted_files = []

        for line in diff_index.splitlines():
            if not line.strip():
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0].strip()
            file_path = parts[1].strip()

            # Skip non-Python files for now
            if not file_path.endswith(".py"):
                continue

            if status.startswith("A"):
                added_files.append(file_path)
            elif status.startswith("M"):
                modified_files.append(file_path)
            elif status.startswith("D"):
                deleted_files.append(file_path)

        return {
            "added": added_files,
            "modified": modified_files,
            "deleted": deleted_files,
        }
    except GitCommandError as e:
        logger.error(f"Git command error when getting changed files: {e}")
        return {"added": [], "modified": [], "deleted": []}
    except Exception as e:
        logger.error(f"Unexpected error when getting changed files: {e}")
        return {"added": [], "modified": [], "deleted": []}


def delete_file_chunks_from_db(db_table, repo_url: str, file_paths: List[str]) -> int:
    """
    Deletes all chunks from the database that belong to the specified files.

    Args:
        db_table: The LanceDB table object.
        repo_url: The URL of the repository.
        file_paths: List of file paths to delete chunks for.

    Returns:
        The number of chunks deleted.
    """
    if not file_paths:
        return 0

    try:
        # Build a filter condition to match chunks from these files
        # LanceDB supports filtering with SQL-like WHERE clauses
        file_conditions = [f"file_path = '{file_path}'" for file_path in file_paths]
        filter_condition = (
            f"repo_url = '{repo_url}' AND ({' OR '.join(file_conditions)})"
        )

        # Get the count of matching rows before deletion
        count_before = len(db_table.search().where(filter_condition).to_list())

        # Delete the matching rows
        db_table.delete(filter_condition)

        # Verify deletion by counting again
        count_after = len(db_table.search().where(filter_condition).to_list())
        deleted_count = count_before - count_after

        logger.info(
            f"Deleted {deleted_count} chunks for {len(file_paths)} files from the database."
        )
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting chunks from database: {e}")
        return 0


def process_and_add_file_chunks(
    db_table,
    repo_url: str,
    local_repo_path: str,
    file_paths: List[str],
    embedding_model,
) -> int:
    """
    Processes the specified files, extracts code chunks, generates embeddings,
    and adds them to the database.

    Args:
        db_table: The LanceDB table object.
        repo_url: The URL of the repository.
        local_repo_path: The local path to the repository.
        file_paths: List of file paths to process.
        embedding_model: The embedding model to use.

    Returns:
        The number of chunks added.
    """
    if not file_paths:
        return 0

    all_chunks_to_add = []

    for file_path in file_paths:
        try:
            full_path = os.path.join(local_repo_path, file_path)
            if not os.path.exists(full_path):
                logger.warning(
                    f"Warning: File {file_path} does not exist at {full_path}"
                )
                continue

            logger.info(f"Processing file: {file_path}")

            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Get code chunks (functions, classes)
            code_chunks = parse_and_extract_chunks(file_path, content)

            # Embed each chunk and prepare for DB insertion
            for chunk in code_chunks:
                embedding = get_embedding(chunk["code"], embedding_model)
                if embedding is not None:
                    chunk_schema_item = CodeChunkSchema(
                        id=chunk["id"],
                        repo_url=repo_url,
                        file_path=chunk["file_path"],
                        code_chunk=chunk["code"],
                        embedding=embedding,
                        start_line=chunk["start_line"],
                        end_line=chunk["end_line"],
                    )
                    all_chunks_to_add.append(chunk_schema_item)
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

    # Add all chunks to the database in a single batch
    if all_chunks_to_add:
        try:
            db_table.add(all_chunks_to_add)
            logger.info(
                f"Added {len(all_chunks_to_add)} chunks from {len(file_paths)} files to the database."
            )
            return len(all_chunks_to_add)
        except Exception as e:
            logger.error(f"Error adding chunks to database: {e}")
            return 0
    else:
        logger.info(f"No chunks to add from {len(file_paths)} files.")
        return 0


def incremental_index_repository(
    repo_url: str, old_commit: str, new_commit: str
) -> Dict[str, int]:
    """
    Orchestrates the incremental indexing pipeline for a repository.

    Args:
        repo_url: The URL of the Git repository to index.
        old_commit: The SHA or reference of the old commit.
        new_commit: The SHA or reference of the new commit.

    Returns:
        A dictionary with statistics about the indexing process.
    """
    logger.info(
        f"--- Starting incremental indexing for repository: {repo_url} between {old_commit} and {new_commit} ---"
    )
    logger.info(f"Comparing changes between {old_commit} and {new_commit}")
    start_time = time.time()

    # 1. Load Configuration from Pydantic settings
    repo_clone_dir = settings.REPO_CLONE_DIR
    lancedb_path = settings.LANCEDB_PATH
    embedding_model_name = settings.EMBEDDING_MODEL_NAME

    # Derive a local path for the repo from its URL
    repo_name = "/".join(repo_url.split("/")[-2:]).replace(".git", "")
    table_name = repo_url_to_table_name(repo_url)

    local_repo_path = os.path.join(repo_clone_dir, repo_name)

    # Initialize Services (Embedding Model and DB)
    logger.info("\nStep 1: Initializing services and repository...")
    try:
        embedding_model = initialize_embedding_model(embedding_model_name)
        db_conn = get_lancedb_conn(lancedb_path)
        code_table = create_code_table_if_not_exists(db_conn, table_name)

        if code_table is None:
            logger.error("Failed to create or open LanceDB table. Aborting.")
            return {
                "status": "error",
                "error": "Failed to create or open LanceDB table",
                "elapsed_time": time.time() - start_time,
            }
    except Exception as e:
        logger.error(f"Error during service/repo initialization: {e}. Aborting.")
        return {
            "status": "error",
            "error": f"Service initialization failed: {str(e)}",
            "elapsed_time": time.time() - start_time,
        }
    logger.info("Services and repository initialized successfully.")

    # Clone or Pull Repository
    logger.info(f"\nStep 2: Ensuring repository is up-to-date at {local_repo_path}...")
    repo = clone_or_pull_repository(repo_url, local_repo_path)
    if not repo:
        logger.error("Failed to clone or update repository. Aborting.")
        return {
            "status": "error",
            "error": "Failed to clone or update repository",
            "elapsed_time": time.time() - start_time,
        }
    logger.info("Repository ready.")

    # Identify Changed Files
    logger.info("\nStep 3: Identifying changed files...")
    changed_files = get_changed_files(repo, old_commit, new_commit)

    added_count = len(changed_files["added"])
    modified_count = len(changed_files["modified"])
    deleted_count = len(changed_files["deleted"])

    logger.info(
        f"Found {added_count} added, {modified_count} modified, and {deleted_count} deleted Python files."
    )

    # Process Deleted and Modified Files (remove from DB)
    logger.info("\nStep 4: Removing chunks for deleted and modified files...")
    files_to_delete = changed_files["deleted"] + changed_files["modified"]
    deleted_chunks = delete_file_chunks_from_db(code_table, repo_url, files_to_delete)

    # Process Added and Modified Files (add to DB)
    logger.info("\nStep 5: Processing and adding chunks for new and modified files...")
    files_to_add = changed_files["added"] + changed_files["modified"]
    added_chunks = process_and_add_file_chunks(
        code_table, repo_url, local_repo_path, files_to_add, embedding_model
    )

    end_time = time.time()
    elapsed_time = end_time - start_time

    logger.info(
        f"\n--- Incremental indexing finished in {elapsed_time:.2f} seconds. ---"
    )
    logger.info("Summary:")
    logger.info(
        f"  - Files: {added_count} added, {modified_count} modified, {deleted_count} deleted"
    )
    logger.info(f"  - Chunks: {deleted_chunks} removed, {added_chunks} added")
    logger.info(f"Total rows in table '{table_name}': {len(code_table)}")

    return {
        "status": "success",
        "files_added": added_count,
        "files_modified": modified_count,
        "files_deleted": deleted_count,
        "chunks_deleted": deleted_chunks,
        "chunks_added": added_chunks,
        "total_chunks": len(code_table),
        "elapsed_time": elapsed_time,
    }


# Example usage: Run this script directly to test incremental indexing
if __name__ == "__main__":
    # A small, well-known repository is a good example
    EXAMPLE_REPO_URL = "https://github.com/pallets/flask.git"
    # You would typically get these from a webhook payload or other event source
    # For testing, find two commit SHAs from the EXAMPLE_REPO_URL
    # e.g., by cloning the repo and running `git log --oneline`
    OLD_COMMIT_SHA = "<PASTE_OLD_COMMIT_SHA_HERE>"  # Replace with an actual commit SHA
    NEW_COMMIT_SHA = "<PASTE_NEW_COMMIT_SHA_HERE>"  # Replace with a newer commit SHA

    # Setup basic logging for the script execution
    from app.core.logging_config import (
        setup_logging,  # Import here for standalone script execution
    )

    setup_logging()
    logger.info("Running incremental_indexer.py directly.")

    # Access settings (Pydantic settings automatically loads .env)
    logger.info(f"Using REPO_CLONE_DIR: {settings.REPO_CLONE_DIR}")
    logger.info(f"Using LANCEDB_PATH: {settings.LANCEDB_PATH}")
    logger.info(f"Using EMBEDDING_MODEL_NAME: {settings.EMBEDDING_MODEL_NAME}")

    if (
        OLD_COMMIT_SHA == "<PASTE_OLD_COMMIT_SHA_HERE>"
        or NEW_COMMIT_SHA == "<PASTE_NEW_COMMIT_SHA_HERE>"
    ):
        logger.error("Please replace placeholder commit SHAs in the __main__ block.")
    else:
        stats = incremental_index_repository(
            EXAMPLE_REPO_URL, OLD_COMMIT_SHA, NEW_COMMIT_SHA
        )
        logger.info(f"Incremental indexing complete. Stats: {stats}")
