import os
# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import time
from typing import Dict, List
from dotenv import load_dotenv

# Import the necessary functions from our other modules
from git import Repo, GitCommandError
from app.repo_manager import clone_or_pull_repository
from app.code_parser import parse_and_extract_chunks
from app.embedding_generator import initialize_embedding_model, get_embedding
from app.vector_store import get_lancedb_conn, create_code_table_if_not_exists, CodeChunkSchema

# Load environment variables from .env file
load_dotenv()

def get_changed_files(repo: Repo, old_commit: str, new_commit: str) -> Dict[str, List[str]]:
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
        diff_index = repo.git.diff('--name-status', old_commit, new_commit)
        
        # Parse the diff output
        added_files = []
        modified_files = []
        deleted_files = []
        
        for line in diff_index.splitlines():
            if not line.strip():
                continue
                
            parts = line.split('\t')
            if len(parts) < 2:
                continue
                
            status = parts[0].strip()
            file_path = parts[1].strip()
            
            # Skip non-Python files for now
            if not file_path.endswith('.py'):
                continue
                
            if status.startswith('A'):
                added_files.append(file_path)
            elif status.startswith('M'):
                modified_files.append(file_path)
            elif status.startswith('D'):
                deleted_files.append(file_path)
        
        return {
            'added': added_files,
            'modified': modified_files,
            'deleted': deleted_files
        }
    except GitCommandError as e:
        print(f"Git command error when getting changed files: {e}")
        return {'added': [], 'modified': [], 'deleted': []}
    except Exception as e:
        print(f"Unexpected error when getting changed files: {e}")
        return {'added': [], 'modified': [], 'deleted': []}

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
        filter_condition = f"repo_url = '{repo_url}' AND ({' OR '.join(file_conditions)})"
        
        # Get the count of matching rows before deletion
        count_before = len(db_table.search().where(filter_condition).to_list())
        
        # Delete the matching rows
        db_table.delete(filter_condition)
        
        # Verify deletion by counting again
        count_after = len(db_table.search().where(filter_condition).to_list())
        deleted_count = count_before - count_after
        
        print(f"Deleted {deleted_count} chunks for {len(file_paths)} files from the database.")
        return deleted_count
    except Exception as e:
        print(f"Error deleting chunks from database: {e}")
        return 0

def process_and_add_file_chunks(
    db_table, 
    repo_url: str, 
    local_repo_path: str, 
    file_paths: List[str], 
    embedding_model
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
                print(f"Warning: File {file_path} does not exist at {full_path}")
                continue
                
            print(f"Processing file: {file_path}")
            
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # Get code chunks (functions, classes)
            code_chunks = parse_and_extract_chunks(file_path, content)
            
            # Embed each chunk and prepare for DB insertion
            for chunk in code_chunks:
                embedding = get_embedding(chunk['code'], embedding_model)
                if embedding is not None:
                    chunk_schema_item = CodeChunkSchema(
                        id=chunk['id'],
                        repo_url=repo_url,
                        file_path=chunk['file_path'],
                        code_chunk=chunk['code'],
                        embedding=embedding,
                        start_line=chunk['start_line'],
                        end_line=chunk['end_line']
                    )
                    all_chunks_to_add.append(chunk_schema_item)
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
    
    # Add all chunks to the database in a single batch
    if all_chunks_to_add:
        try:
            db_table.add(all_chunks_to_add)
            print(f"Added {len(all_chunks_to_add)} chunks from {len(file_paths)} files to the database.")
            return len(all_chunks_to_add)
        except Exception as e:
            print(f"Error adding chunks to database: {e}")
            return 0
    else:
        print(f"No chunks to add from {len(file_paths)} files.")
        return 0

def incremental_index_repository(repo_url: str, old_commit: str, new_commit: str) -> Dict[str, int]:
    """
    Orchestrates the incremental indexing pipeline for a repository.
    
    Args:
        repo_url: The URL of the Git repository to index.
        old_commit: The SHA or reference of the old commit.
        new_commit: The SHA or reference of the new commit.
        
    Returns:
        A dictionary with statistics about the indexing process.
    """
    print(f"--- Starting incremental indexing for repository: {repo_url} ---")
    print(f"Comparing changes between {old_commit} and {new_commit}")
    start_time = time.time()
    
    # Load Configuration
    repo_clone_dir = os.getenv("REPO_CLONE_DIR", "./repos")
    lancedb_path = os.getenv("LANCEDB_PATH", "./lancedb_data/db")
    embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    table_name = "code_embeddings"
    
    # Derive a local path for the repo from its URL
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    local_repo_path = os.path.join(repo_clone_dir, repo_name)
    
    # Initialize Services (Embedding Model and DB)
    print("\nStep 1: Initializing services...")
    try:
        embedding_model = initialize_embedding_model(embedding_model_name)
        db_conn = get_lancedb_conn(lancedb_path)
        code_table = create_code_table_if_not_exists(db_conn, table_name)
        
        if code_table is None:
            print("Error: Failed to create or open LanceDB table. Aborting.")
            return {
                'status': 'error',
                'error': 'Failed to create or open LanceDB table',
                'elapsed_time': time.time() - start_time
            }
    except Exception as e:
        print(f"Error during service initialization: {e}. Aborting.")
        return {
            'status': 'error',
            'error': f'Service initialization failed: {str(e)}',
            'elapsed_time': time.time() - start_time
        }
    print("Services initialized successfully.")
    
    # Clone or Pull Repository
    print(f"\nStep 2: Ensuring repository is up-to-date at {local_repo_path}...")
    repo = clone_or_pull_repository(repo_url, local_repo_path)
    if not repo:
        print("Error: Failed to clone or update repository. Aborting.")
        return {
            'status': 'error',
            'error': 'Failed to clone or update repository',
            'elapsed_time': time.time() - start_time
        }
    print("Repository ready.")
    
    # Identify Changed Files
    print("\nStep 3: Identifying changed files...")
    changed_files = get_changed_files(repo, old_commit, new_commit)
    
    added_count = len(changed_files['added'])
    modified_count = len(changed_files['modified'])
    deleted_count = len(changed_files['deleted'])
    
    print(f"Found {added_count} added, {modified_count} modified, and {deleted_count} deleted Python files.")
    
    # Process Deleted and Modified Files (remove from DB)
    print("\nStep 4: Removing chunks for deleted and modified files...")
    files_to_delete = changed_files['deleted'] + changed_files['modified']
    deleted_chunks = delete_file_chunks_from_db(code_table, repo_url, files_to_delete)
    
    # Process Added and Modified Files (add to DB)
    print("\nStep 5: Processing and adding chunks for new and modified files...")
    files_to_add = changed_files['added'] + changed_files['modified']
    added_chunks = process_and_add_file_chunks(
        code_table, repo_url, local_repo_path, files_to_add, embedding_model
    )
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print(f"\n--- Incremental indexing finished in {elapsed_time:.2f} seconds. ---")
    print("Summary:")
    print(f"  - Files: {added_count} added, {modified_count} modified, {deleted_count} deleted")
    print(f"  - Chunks: {deleted_chunks} removed, {added_chunks} added")
    print(f"  - Total rows in table '{table_name}': {len(code_table)}")
    
    return {
        'status': 'success',
        'files_added': added_count,
        'files_modified': modified_count,
        'files_deleted': deleted_count,
        'chunks_deleted': deleted_chunks,
        'chunks_added': added_chunks,
        'total_chunks': len(code_table),
        'elapsed_time': elapsed_time
    }

# Example usage: Run this script directly to test incremental indexing
if __name__ == "__main__":
    # A small, well-known repository is a good example
    sample_repo_url = "https://github.com/rekib0023/testing-rkb0023.git"
    
    # For testing, we'll use HEAD~1 (previous commit) and HEAD (latest commit)
    old_commit = "HEAD~1"
    new_commit = "HEAD"
    
    # Before running, ensure your .env file is set up with:
    # REPO_CLONE_DIR, LANCEDB_PATH, EMBEDDING_MODEL_NAME
    if not all(os.getenv(k) for k in ["REPO_CLONE_DIR", "LANCEDB_PATH", "EMBEDDING_MODEL_NAME"]):
        print("Error: Please ensure REPO_CLONE_DIR, LANCEDB_PATH, and EMBEDDING_MODEL_NAME are set in your .env file.")
    else:
        incremental_index_repository(sample_repo_url, old_commit, new_commit)
