import argparse
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

# Import the necessary functions from our other modules
from app.embedding_generator import get_embedding, get_embedding_model
from app.vector_store import get_lancedb_conn

# Load environment variables from .env file
load_dotenv()


class CodeQueryEngine:
    """
    A query engine for retrieving code chunks based on semantic similarity.
    """

    def __init__(
        self,
        lancedb_path: str = None,
        embedding_model_name: str = None,
        table_name: str = "code_embeddings",
    ):
        """
        Initialize the query engine with the LanceDB connection and embedding model.

        Args:
            lancedb_path: Path to the LanceDB database. If None, uses the LANCEDB_PATH env var.
            embedding_model_name: Name of the embedding model to use. If None, uses the EMBEDDING_MODEL_NAME env var.
            table_name: Name of the table containing the code embeddings.
        """
        # Load configuration from environment variables if not provided
        self.lancedb_path = lancedb_path or os.getenv(
            "LANCEDB_PATH", "./lancedb_data/db"
        )
        self.embedding_model_name = embedding_model_name or os.getenv(
            "EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"
        )
        self.table_name = table_name

        # Initialize the embedding model
        self.embedding_model = get_embedding_model(self.embedding_model_name)

        # Connect to LanceDB
        self.db_conn = get_lancedb_conn(self.lancedb_path)

        # Open the table
        try:
            self.table = self.db_conn.open_table(self.table_name)
            print(
                f"Successfully opened table '{self.table_name}' with {len(self.table)} code chunks."
            )
        except Exception as e:
            print(f"Error opening table '{self.table_name}': {e}")
            print(
                "Have you indexed any repositories yet? Run the indexer.py script first."
            )
            self.table = None

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query the database for code chunks similar to the query text.

        Args:
            query_text: The query text to search for.
            top_k: The number of results to return.

        Returns:
            A list of dictionaries containing the code chunks and their metadata.
        """
        if not self.table:
            print("Error: No table available for querying.")
            return []

        # Generate embedding for the query
        query_embedding = get_embedding(query_text, self.embedding_model)
        if query_embedding is None:
            print("Error: Failed to generate embedding for query.")
            return []

        # Perform the search
        try:
            results = (
                self.table.search(query_embedding)
                .limit(top_k)
                .select(
                    [
                        "id",
                        "repo_url",
                        "file_path",
                        "code_chunk",
                        "start_line",
                        "end_line",
                        "_distance",
                    ]
                )
                .to_list()
            )
            return results
        except Exception as e:
            print(f"Error performing search: {e}")
            return []

    def format_results(self, results: List[Dict[str, Any]]) -> str:
        """
        Format the search results into a readable string.

        Args:
            results: The search results from the query method.

        Returns:
            A formatted string representation of the results.
        """
        if not results:
            return "No results found."

        formatted_output = "\n" + "=" * 80 + "\n"
        formatted_output += f"Found {len(results)} relevant code chunks:\n"
        formatted_output += "=" * 80 + "\n\n"

        for i, result in enumerate(results):
            similarity_score = 1.0 - result.get("_distance", 0)
            formatted_output += f"Result {i + 1} [Similarity: {similarity_score:.4f}]\n"
            formatted_output += f"File: {result.get('file_path')}\n"
            formatted_output += (
                f"Lines: {result.get('start_line')}-{result.get('end_line')}\n"
            )
            formatted_output += f"Repository: {result.get('repo_url')}\n"
            formatted_output += "-" * 80 + "\n"
            formatted_output += result.get("code_chunk", "") + "\n"
            formatted_output += "=" * 80 + "\n\n"

        return formatted_output


def interactive_mode(query_engine: CodeQueryEngine):
    """Run an interactive query session."""
    print(
        "\nEntering interactive query mode. Type 'exit' or 'quit' to end the session."
    )
    print("Type 'help' for available commands.\n")

    while True:
        query = input("\nEnter your query: ").strip()

        if query.lower() in ("exit", "quit"):
            print("Exiting interactive mode.")
            break

        if query.lower() == "help":
            print("\nAvailable commands:")
            print("  help - Show this help message")
            print("  exit, quit - Exit interactive mode")
            print("  Any other text will be treated as a query to search the codebase")
            continue

        if not query:
            continue

        results = query_engine.query(query)
        print(query_engine.format_results(results))


def main():
    parser = argparse.ArgumentParser(description="Query the indexed code repository.")
    parser.add_argument("--query", "-q", type=str, help="The query to search for.")
    parser.add_argument(
        "--top-k", "-k", type=int, default=5, help="Number of results to return."
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Run in interactive mode."
    )

    args = parser.parse_args()

    # Initialize the query engine
    query_engine = CodeQueryEngine()

    if not query_engine.table:
        return

    if args.interactive:
        interactive_mode(query_engine)
    elif args.query:
        results = query_engine.query(args.query, args.top_k)
        print(query_engine.format_results(results))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
