import os
import time

from dotenv import load_dotenv

from app.code_parser import parse_and_extract_chunks
from app.embedding_generator import get_embedding, initialize_embedding_model
from app.repo_manager import clone_or_pull_repository
from app.utils import repo_url_to_table_name
from app.vector_store import (
    CodeChunkSchema,
    create_code_table_if_not_exists,
    drop_table,
    get_lancedb_conn,
)

# Load environment variables from .env file
load_dotenv()


def index_repository(repo_url: str):
    """
    Orchestrates the full pipeline of cloning, parsing, embedding, and indexing a repository.

    Args:
        repo_url: The URL of the Git repository to index.
    """
    print(f"--- Starting indexing process for repository: {repo_url} ---")
    start_time = time.time()

    # 1. Load Configuration
    repo_clone_dir = os.getenv("REPO_CLONE_DIR", "./repos")
    lancedb_path = os.getenv("LANCEDB_PATH", "./lancedb_data/db")
    embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

    # Derive a local path for the repo from its URL
    repo_name = "/".join(repo_url.split("/")[-2:]).replace(".git", "")
    table_name = repo_url_to_table_name(repo_url)

    local_repo_path = os.path.join(repo_clone_dir, repo_name)

    # 2. Initialize Services (Embedding Model and DB)
    print("\nStep 1: Initializing services...")
    try:
        embedding_model = initialize_embedding_model(embedding_model_name)
        db_conn = get_lancedb_conn(lancedb_path)
        # Drop the table to ensure a clean run, making the process idempotent
        drop_table(db_conn, table_name)
        code_table = create_code_table_if_not_exists(db_conn, table_name)

        # Now that we understand the issue, we can remove the debugging code
        # and use an explicit check for None
        if code_table is None:
            print("Error: Failed to create or open LanceDB table. Aborting.")
            return
    except Exception as e:
        print(f"Error during service initialization: {e}. Aborting.")
        return
    print("Services initialized successfully.")

    # 3. Clone or Pull Repository
    print(f"\nStep 2: Cloning/pulling repository into {local_repo_path}...")
    repo = clone_or_pull_repository(repo_url, local_repo_path)
    if not repo:
        print("Error: Failed to clone repository. Aborting.")
        return
    print("Repository ready.")

    # 4. Walk Filesystem, Parse, Embed, and Prepare Data
    print("\nStep 3: Parsing, embedding, and preparing data...")
    all_chunks_to_add = []
    files_processed = 0
    for root, _, files in os.walk(local_repo_path):
        # Skip .git directory
        if ".git" in root:
            continue

        for file in files:
            # For now, we only process Python files
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                relative_file_path = os.path.relpath(file_path, local_repo_path)
                print(f"  - Processing file: {relative_file_path}")
                files_processed += 1
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Get code chunks (functions, classes)
                    code_chunks = parse_and_extract_chunks(relative_file_path, content)

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
                    print(f"    - Error processing file {relative_file_path}: {e}")

    print(
        f"Data preparation complete. Found {len(all_chunks_to_add)} chunks in {files_processed} Python files."
    )

    # 5. Batch Insert into LanceDB
    if all_chunks_to_add:
        print("\nStep 4: Adding data to LanceDB...")
        try:
            # LanceDB's add method can take a list of Pydantic objects directly
            code_table.add(all_chunks_to_add)
            print(
                f"Successfully added {len(all_chunks_to_add)} chunks to the '{table_name}' table."
            )
        except Exception as e:
            print(f"Error adding data to LanceDB: {e}")
    else:
        print("\nStep 4: No new chunks to add to LanceDB.")

    end_time = time.time()
    print(
        f"\n--- Indexing process finished in {end_time - start_time:.2f} seconds. ---"
    )
    print(f"Total rows in table '{table_name}': {len(code_table)}")


# Example usage: Run this script directly to index a repository
if __name__ == "__main__":
    # A small, well-known repository is a good example
    # For example, the 'requests' library
    sample_repo_url = "https://github.com/psf/requests.git"

    # Before running, ensure your .env file is set up with:
    # REPO_CLONE_DIR, LANCEDB_PATH, EMBEDDING_MODEL_NAME
    if not all(
        os.getenv(k) for k in ["REPO_CLONE_DIR", "LANCEDB_PATH", "EMBEDDING_MODEL_NAME"]
    ):
        print(
            "Error: Please ensure REPO_CLONE_DIR, LANCEDB_PATH, and EMBEDDING_MODEL_NAME are set in your .env file."
        )
    else:
        index_repository(sample_repo_url)
