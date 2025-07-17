import os
import time
from typing import Any, Dict, List

from git import GitCommandError, Repo

from app.core.config import get_settings
from app.core.exceptions import (
    RepositoryCloneError,
    RepositoryIndexingError,
    VectorDBError,
)
from app.core.logging_config import get_logger
from app.indexing.code_parser import parse_and_extract_chunks
from app.indexing.embedding_generator import get_embedding, get_embedding_model
from app.storage.repo_manager import clone_or_pull_repository
from app.storage.vector_store import (
    CodeChunkSchema,
    create_code_table_if_not_exists,
    get_lancedb_conn,
)
from app.utils.general_utils import repo_url_to_table_name

logger = get_logger(__name__)


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

    Raises:
        RepositoryIndexingError: If there's an error retrieving or processing the diff
    """
    try:
        # Get the diff between the two commits
        logger.debug(
            f"Getting diff between commits {old_commit[:7]} and {new_commit[:7]}"
        )
        diff_index = repo.git.diff("--name-status", old_commit, new_commit)

        # Parse the diff output
        added_files = []
        modified_files = []
        deleted_files = []

        for line in diff_index.splitlines():
            if not line.strip():
                continue

            # Parse the line: Format is STATUS\tFILENAME
            parts = line.strip().split("\t")
            if len(parts) < 2:
                logger.warning(f"Unexpected diff format in line: {line}. Skipping.")
                continue

            status, path = parts[0], parts[1]

            # Only include Python files for this example
            if not path.endswith(".py"):
                continue

            # Categorize based on Git status
            if status.startswith("A"):  # Added
                added_files.append(path)
            elif status.startswith("M"):  # Modified
                modified_files.append(path)
            elif status.startswith("D"):  # Deleted
                deleted_files.append(path)
            # You could handle renamed files ('R') differently if needed

        logger.debug(
            f"Found {len(added_files)} added, {len(modified_files)} modified, and {len(deleted_files)} deleted Python files"
        )
        return {
            "added": added_files,
            "modified": modified_files,
            "deleted": deleted_files,
        }

    except GitCommandError as e:
        error_msg = f"Git command error when getting changed files: {str(e)}"
        logger.error(error_msg)
        raise RepositoryIndexingError(
            repo.working_dir if hasattr(repo, "working_dir") else "unknown", error_msg
        ) from e
    except Exception as e:
        error_msg = f"Unexpected error when getting changed files: {str(e)}"
        logger.exception(error_msg)
        raise RepositoryIndexingError(
            repo.working_dir if hasattr(repo, "working_dir") else "unknown", error_msg
        ) from e


def delete_file_chunks_from_db(db_table, repo_url: str, file_paths: List[str]) -> int:
    """
    Deletes chunks related to specific file paths from a LanceDB table.

    Args:
        db_table: A LanceDB table instance.
        repo_url: The repository URL associated with the chunks.
        file_paths: A list of file paths to delete chunks for.

    Returns:
        The number of deleted chunks.

    Raises:
        VectorDBError: If there's an error when interacting with the vector database
    """
    # If no files to delete, return early
    if not file_paths:
        return 0

    try:
        # Prepare the query
        query_conditions = []
        for file_path in file_paths:
            # Escape single quotes in the path to avoid SQL injection
            safe_path = file_path.replace("'", "''")
            query_conditions.append(
                f"(repo_url = '{repo_url}' AND file_path = '{safe_path}')"
            )

        # Combine conditions with OR
        query = " OR ".join(query_conditions)
        logger.debug(f"Delete query: {query}")

        # Check how many rows will be affected
        try:
            data = db_table.search().where(query).to_pandas()
            deleted_count = len(data)
        except Exception as e:
            logger.warning(f"Unable to count chunks before deletion: {str(e)}")
            deleted_count = -1  # Indicate we don't know how many will be deleted

        # Delete the chunks
        db_table.delete(query)
        if deleted_count >= 0:
            logger.debug(f"Deleted {deleted_count} chunks from LanceDB table")
        else:
            logger.debug("Deleted chunks from LanceDB table (count unknown)")

        return deleted_count if deleted_count >= 0 else 0

    except Exception as e:
        error_msg = f"Error deleting chunks from vector database: {str(e)}"
        logger.exception(error_msg)
        raise VectorDBError("chunk_deletion", error_msg) from e


def process_and_add_file_chunks(
    db_table,
    repo_url: str,
    repo_local_path: str,
    file_paths: List[str],
    embedding_model,
) -> int:
    """
    Processes the content of the given files and adds the resulting chunks to the database.

    Args:
        db_table: A LanceDB table instance.
        repo_url: The repository URL associated with the chunks.
        repo_local_path: The local path to the repository.
        file_paths: A list of file paths to process and add chunks for.
        embedding_model: The embedding model to use for generating embeddings.

    Returns:
        The number of chunks added to the database.

    Raises:
        VectorDBError: If there's an error when adding chunks to the vector database
        RepositoryIndexingError: If there's an error processing files or extracting chunks
    """
    # If no files to add, return early
    if not file_paths:
        return 0

    added_chunks = 0
    errors = []

    for file_path in file_paths:
        try:
            # Build the full path to the file
            full_path = os.path.join(repo_local_path, file_path)
            if not os.path.exists(full_path):
                logger.warning(f"File not found at {full_path}. Skipping.")
                continue

            # Read the file content
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
            except UnicodeDecodeError:
                logger.warning(f"File {file_path} is not UTF-8 encoded. Skipping.")
                continue
            except IOError as e:
                error_msg = f"IO error reading file {file_path}: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue

            # Extract chunks from the content
            try:
                chunks = parse_and_extract_chunks(file_content, file_path)
                if not chunks:
                    logger.debug(f"No chunks extracted from {file_path}. Skipping.")
                    continue
            except Exception as e:
                error_msg = f"Error parsing file {file_path}: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue

            # Prepare data for the database
            db_rows = []
            for chunk in chunks:
                try:
                    # Generate embedding for the chunk
                    embedding = get_embedding(chunk.content, embedding_model)

                    # Create schema instance
                    db_row = CodeChunkSchema(
                        repo_url=repo_url,
                        file_path=file_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        content=chunk.content,
                        symbol_type=chunk.symbol_type,
                        symbol_name=chunk.symbol_name,
                        embedding=embedding,
                    )
                    db_rows.append(db_row.model_dump())
                except Exception as e:
                    error_msg = (
                        f"Error generating embedding for chunk in {file_path}: {str(e)}"
                    )
                    logger.warning(error_msg)
                    # Continue with other chunks even if one fails

            # Add chunks to the database
            if db_rows:
                try:
                    db_table.add(db_rows)
                    added_chunks += len(db_rows)
                    logger.debug(f"Added {len(db_rows)} chunks from {file_path}")
                except Exception as e:
                    error_msg = (
                        f"Error adding chunks to database for {file_path}: {str(e)}"
                    )
                    logger.warning(error_msg)
                    errors.append(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error processing file {file_path}: {str(e)}"
            logger.exception(error_msg)
            errors.append(error_msg)

    # If any errors occurred but some chunks were still added, log the issues but don't fail
    if errors and added_chunks > 0:
        logger.warning(
            f"Completed with {len(errors)} errors. Added {added_chunks} chunks."
        )
    # If only errors occurred and no chunks were added, raise an exception
    elif errors and added_chunks == 0:
        error_summary = (
            f"Failed to add any chunks to database. Errors: {'; '.join(errors[:3])}"
        )
        if len(errors) > 3:
            error_summary += f" and {len(errors) - 3} more"
        raise VectorDBError("chunk_addition", error_summary)

    return added_chunks


def incremental_index_repository(
    repo_url: str, old_commit: str, new_commit: str
) -> Dict[str, Any]:
    """
    Orchestrates the incremental indexing pipeline for a repository.

    Args:
        repo_url: The URL of the Git repository to index.
        old_commit: The SHA or reference of the old commit.
        new_commit: The SHA or reference of the new commit.

    Returns:
        A dictionary with statistics about the indexing process.

    Raises:
        RepositoryCloneError: If cloning/pulling the repository fails
        RepositoryIndexingError: If indexing the repository fails
        VectorDBError: If operations with the vector database fail
    """
    logger.info(
        f"--- Starting incremental indexing for repository: {repo_url} between {old_commit} and {new_commit} ---"
    )
    logger.info(f"Comparing changes between {old_commit[:7]} and {new_commit[:7]}")
    start_time = time.time()

    # Get settings using the singleton accessor
    settings = get_settings()

    # 1. Load Configuration from settings
    repo_clone_dir = settings.REPO_CLONE_DIR
    lancedb_path = settings.LANCEDB_PATH
    embedding_model_name = settings.EMBEDDING_MODEL_NAME

    # Derive a local path for the repo from its URL
    repo_name = "/".join(repo_url.split("/")[-2:]).replace(".git", "")
    table_name = repo_url_to_table_name(repo_url)
    local_repo_path = os.path.join(repo_clone_dir, repo_name)

    # Initialize Services (Embedding Model and DB)
    logger.info("\nStep 1: Initializing services...")
    try:
        # Initialize embedding model
        try:
            embedding_model = (
                get_embedding_model()
            )  # Factory function handles model name from settings
            logger.debug(
                f"Successfully initialized embedding model: {embedding_model_name}"
            )
        except Exception as e:
            error_msg = f"Failed to initialize embedding model '{embedding_model_name}': {str(e)}"
            logger.exception(error_msg)
            raise RepositoryIndexingError(repo_url, error_msg) from e

        # Initialize vector database connection
        try:
            db_conn = get_lancedb_conn(lancedb_path)
            code_table = create_code_table_if_not_exists(db_conn, table_name)
            if code_table is None:
                error_msg = f"Failed to create or open LanceDB table '{table_name}'"
                logger.error(error_msg)
                raise VectorDBError("table_creation", error_msg)
            logger.debug(
                f"Successfully connected to vector DB and accessed table: {table_name}"
            )
        except Exception as e:
            if not isinstance(e, VectorDBError):
                error_msg = f"Vector database error: {str(e)}"
                logger.exception(error_msg)
                raise VectorDBError("connection", error_msg) from e
            raise
    except (RepositoryIndexingError, VectorDBError):
        # Re-raise these exceptions to be caught at a higher level
        raise
    except Exception as e:
        error_msg = f"Unexpected error during service initialization: {str(e)}"
        logger.exception(error_msg)
        raise RepositoryIndexingError(repo_url, error_msg) from e

    logger.info("Services initialized successfully")

    # Clone or Pull Repository
    logger.info(f"\nStep 2: Ensuring repository is up-to-date at {local_repo_path}...")
    try:
        repo = clone_or_pull_repository(repo_url, local_repo_path)
        if not repo:
            error_msg = f"Failed to clone or update repository at {local_repo_path}"
            logger.error(error_msg)
            raise RepositoryCloneError(repo_url, error_msg)
        logger.info("Repository ready for indexing")
    except Exception as e:
        if not isinstance(e, RepositoryCloneError):
            error_msg = f"Error accessing repository: {str(e)}"
            logger.exception(error_msg)
            raise RepositoryCloneError(repo_url, error_msg) from e
        raise

    # Track statistics for the final summary
    stats = {
        "status": "success",  # Default to success, will change if errors occur
        "files_added": 0,
        "files_modified": 0,
        "files_deleted": 0,
        "chunks_deleted": 0,
        "chunks_added": 0,
        "elapsed_time": 0,
    }

    try:
        # Identify Changed Files
        logger.info("\nStep 3: Identifying changed files...")
        changed_files = get_changed_files(repo, old_commit, new_commit)

        stats["files_added"] = len(changed_files["added"])
        stats["files_modified"] = len(changed_files["modified"])
        stats["files_deleted"] = len(changed_files["deleted"])

        logger.info(
            f"Found {stats['files_added']} added, {stats['files_modified']} modified, "
            f"and {stats['files_deleted']} deleted Python files."
        )

        # Process Deleted and Modified Files (remove from DB)
        if changed_files["deleted"] or changed_files["modified"]:
            logger.info("\nStep 4: Removing chunks for deleted and modified files...")
            files_to_delete = changed_files["deleted"] + changed_files["modified"]
            try:
                deleted_chunks = delete_file_chunks_from_db(
                    code_table, repo_url, files_to_delete
                )
                stats["chunks_deleted"] = deleted_chunks
                logger.info(
                    f"Successfully removed {deleted_chunks} chunks from database"
                )
            except Exception as e:
                error_msg = f"Error removing file chunks from database: {str(e)}"
                logger.exception(error_msg)
                raise VectorDBError("chunk_deletion", error_msg) from e
        else:
            logger.info("No files to remove from database")

        # Process Added and Modified Files (add to DB)
        if changed_files["added"] or changed_files["modified"]:
            logger.info(
                "\nStep 5: Processing and adding chunks for new and modified files..."
            )
            files_to_add = changed_files["added"] + changed_files["modified"]
            try:
                added_chunks = process_and_add_file_chunks(
                    code_table, repo_url, local_repo_path, files_to_add, embedding_model
                )
                stats["chunks_added"] = added_chunks
                logger.info(f"Successfully added {added_chunks} new chunks to database")
            except Exception as e:
                error_msg = f"Error adding file chunks to database: {str(e)}"
                logger.exception(error_msg)
                raise VectorDBError("chunk_addition", error_msg) from e
        else:
            logger.info("No files to add to database")

        # Update total chunks count
        try:
            stats["total_chunks"] = len(code_table)
        except Exception as e:
            logger.warning(f"Unable to get total chunk count: {str(e)}")
            stats["total_chunks"] = -1  # Indicate count is unknown

    except (RepositoryIndexingError, RepositoryCloneError, VectorDBError):
        stats["status"] = "error"
        raise
    except Exception as e:
        error_msg = f"Unexpected error during incremental indexing: {str(e)}"
        logger.exception(error_msg)
        stats["status"] = "error"
        raise RepositoryIndexingError(repo_url, error_msg) from e
    finally:
        # Always record elapsed time, even if there was an error
        stats["elapsed_time"] = time.time() - start_time

        # Log summary regardless of success/failure
        logger.info(
            f"\n--- Incremental indexing finished in {stats['elapsed_time']:.2f} seconds. ---"
        )
        logger.info("Summary:")
        logger.info(
            f"  - Files: {stats['files_added']} added, {stats['files_modified']} modified, "
            f"{stats['files_deleted']} deleted"
        )
        logger.info(
            f"  - Chunks: {stats['chunks_deleted']} removed, {stats['chunks_added']} added"
        )

        if stats["total_chunks"] >= 0:
            logger.info(f"Total rows in table '{table_name}': {stats['total_chunks']}")

    return stats


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

    # Access settings through Singleton accessor
    settings = get_settings()
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
