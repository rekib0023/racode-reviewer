import logging
import os
from typing import Optional

import lancedb
from lancedb.pydantic import LanceModel, vector

logger = logging.getLogger("app")


class CodeChunkSchema(LanceModel):
    id: str  # Unique identifier for the chunk (e.g., repo_url#file_path#chunk_index)
    repo_url: str
    file_path: str
    code_chunk: str
    embedding: vector(384)  # Dimension for 'all-MiniLM-L6-v2' or similar models.
    start_line: Optional[int] = None
    end_line: Optional[int] = None


def get_lancedb_conn(db_path: str):
    """Connects to or creates a LanceDB database at the given path."""
    # Ensure the parent directory for the db_path exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logger.info(f"Created LanceDB directory: {db_dir}")

    logger.info(f"Connecting to LanceDB at: {db_path}")
    db = lancedb.connect(db_path)
    return db


def drop_table(db_connection, table_name: str):
    """Drops a table from the database if it exists."""
    try:
        db_connection.drop_table(table_name)
        logger.info(f"Successfully dropped table '{table_name}'.")
    except Exception:
        # LanceDB might raise an error if the table doesn't exist, which is fine.
        logger.info(f"Info: Could not drop table '{table_name}' (it may not exist).")


def create_code_table_if_not_exists(
    db_connection, table_name: str
) -> Optional[lancedb.table.Table]:
    """
    Ensures a table exists and returns a handle to it.

    Args:
        db_connection: The LanceDB connection object.
        table_name: The name of the table to create.

    Returns:
        The LanceDB table object or None if the operation failed.
    """
    try:
        if table_name not in db_connection.table_names():
            logger.info(f"Table '{table_name}' does not exist. Creating it...")
            db_connection.create_table(table_name, schema=CodeChunkSchema)
            logger.info(f"Table '{table_name}' created successfully.")
        else:
            logger.info(f"Table '{table_name}' already exists.")

        logger.info(f"Opening table '{table_name}'...")
        tbl = db_connection.open_table(table_name)
        logger.info(f"Successfully opened table '{table_name}'.")
        return tbl
    except Exception as e:
        logger.error(f"Error ensuring table '{table_name}' exists: {e}")
        return None


# Example usage (optional, for testing this module directly)
if __name__ == "__main__":
    test_db_path = "./temp_lancedb"
    test_table_name = "code_embeddings"

    db_conn = get_lancedb_conn(test_db_path)
    if db_conn:
        logger.info(f"Tables before creation: {db_conn.table_names()}")
        table = create_code_table_if_not_exists(db_conn, test_table_name)
        if table:
            logger.info(f"Table schema: {table.schema}")
            logger.info(f"Tables after creation: {db_conn.table_names()}")

            try:
                dummy_data = [
                    CodeChunkSchema(
                        id="test_repo#test_file.py#0",
                        repo_url="test_repo",
                        file_path="test_file.py",
                        code_chunk="def hello():\n  print('world')",
                        embedding=[0.1, 0.2],  # Dummy embedding
                        start_line=1,
                        end_line=2,
                    )
                ]
                table.add(dummy_data)
                logger.info(
                    f"Added dummy data to '{test_table_name}'. Total rows: {len(table)}"
                )
                # print(table.search([0.1, 0.2]).limit(1).to_df())
            except Exception as e:
                logger.error(f"Error adding dummy data: {e}")

    # Clean up the test LanceDB directory
    import shutil

    if os.path.exists(test_db_path):
        logger.info(f"\nCleaning up test LanceDB directory: {test_db_path}")
        shutil.rmtree(test_db_path)
