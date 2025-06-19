import logging
import os
from typing import Any, Dict, List, Optional

from tree_sitter import Language, Parser

# --- Tree-sitter Language Setup ---
# This section helps in locating and loading the compiled tree-sitter language grammar.
# The exact path might vary based on your environment and how tree-sitter-python was installed.

# Option 1: Try to find it in a common location (e.g., a 'build' directory or site-packages)
# You might need to adjust this path or use a more robust discovery mechanism.
LANGUAGE_BUILD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "build", "my-languages.so"
)
PYTHON_LANGUAGE_GRAMMAR_PATH = "tree_sitter_python.language"

_PYTHON_LANG = None
logger = logging.getLogger("app")


def get_python_language() -> Optional[Language]:
    """Loads the Tree-sitter Python language grammar."""
    global _PYTHON_LANG
    if _PYTHON_LANG is not None:
        return _PYTHON_LANG

    try:
        # Attempt to load from a pre-built library if it exists
        if os.path.exists(LANGUAGE_BUILD_PATH):
            _PYTHON_LANG = Language(LANGUAGE_BUILD_PATH, "python")
            logger.info(f"Loaded Python grammar from: {LANGUAGE_BUILD_PATH}")
            return _PYTHON_LANG

        # Fallback: Try to load it assuming tree-sitter-python package handles it
        # This often works if tree-sitter-python correctly installed its grammar.
        # For this to work, you might need to have cloned the tree-sitter-python repo
        # into a 'vendor' directory and run Language.build_library as shown in tree-sitter docs.
        # However, pip install tree-sitter-python often makes it available directly.
        try:
            from tree_sitter_languages import get_language

            _PYTHON_LANG = get_language("python")
            logger.info("Loaded Python grammar using tree-sitter-languages.")
            return _PYTHON_LANG
        except ImportError:
            logger.warning("tree-sitter-languages not found, trying direct import.")
        except Exception as e:
            logger.error(
                f"Could not load Python grammar via tree-sitter-languages: {e}"
            )

        # If the above fails, it implies the grammar isn't readily available.
        # The user might need to ensure tree-sitter-python is correctly installed and its grammar compiled.
        # For a more robust setup, explicitly build the grammar library:
        # Language.build_library(
        #     LANGUAGE_BUILD_PATH,
        #     ['vendor/tree-sitter-python'] # Path to the Python grammar repo
        # )
        # _PYTHON_LANG = Language(LANGUAGE_BUILD_PATH, 'python')
        # print(f"Built and loaded Python grammar to: {LANGUAGE_BUILD_PATH}")
        # return _PYTHON_LANG

        logger.error("Error: Could not load Tree-sitter Python language grammar.")
        logger.error(
            "Please ensure 'tree-sitter-python' is installed and the grammar is compiled."
        )
        logger.error(
            "You may need to run: pip install tree-sitter-languages or manually build the grammar."
        )
        return None

    except Exception as e:
        logger.error(f"An unexpected error occurred while loading Python grammar: {e}")
        return None


# --- Code Chunking Logic ---


def parse_and_extract_chunks(file_path: str, code_content: str) -> List[Dict[str, Any]]:
    """
    Parses Python code using Tree-sitter and extracts functions and classes as chunks.

    Args:
        file_path: The path to the file being parsed (for context).
        code_content: The string content of the Python code.

    Returns:
        A list of dictionaries, where each dictionary represents a code chunk
        (e.g., a function or class) with its name, code, start and end lines.
        Returns an empty list if parsing fails or no relevant chunks are found.
    """
    PY_LANGUAGE = get_python_language()
    if not PY_LANGUAGE:
        return []

    parser = Parser()
    parser.set_language(PY_LANGUAGE)

    try:
        tree = parser.parse(bytes(code_content, "utf8"))
    except Exception as e:
        logger.error(f"Error parsing file {file_path}: {e}")
        return []

    chunks = []

    # Tree-sitter query to find function and class definitions
    # You can expand this query to capture more types of nodes if needed.
    query_string = """
    (function_definition
        name: (identifier) @function.name)
    @function.definition

    (class_definition
        name: (identifier) @class.name)
    @class.definition
    """

    try:
        query = PY_LANGUAGE.query(query_string)
        captures = query.captures(tree.root_node)
    except Exception as e:
        logger.error(f"Error executing tree-sitter query on {file_path}: {e}")
        return []

    # Process captures to extract chunk information
    # We iterate through captures, looking for the main definition nodes
    # and their associated names.
    for node, capture_name in captures:
        if capture_name == "function.definition" or capture_name == "class.definition":
            chunk_type = (
                "function" if capture_name == "function.definition" else "class"
            )
            # Find the corresponding name capture for this definition
            chunk_name_node = None
            for n_cap, cn_cap in captures:
                if (
                    capture_name == "function.definition"
                    and cn_cap == "function.name"
                    and n_cap.parent == node
                ) or (
                    capture_name == "class.definition"
                    and cn_cap == "class.name"
                    and n_cap.parent == node
                ):
                    chunk_name_node = n_cap
                    break

            chunk_name = (
                chunk_name_node.text.decode("utf8")
                if chunk_name_node
                else "<anonymous>"
            )

            start_line = node.start_point[0] + 1  # 0-indexed to 1-indexed
            end_line = node.end_point[0] + 1  # 0-indexed to 1-indexed
            code_text = node.text.decode("utf8")

            chunks.append(
                {
                    "id": f"{file_path}#{chunk_name}#{start_line}-{end_line}",  # Simple unique ID
                    "file_path": file_path,
                    "chunk_name": chunk_name,
                    "type": chunk_type,
                    "code": code_text,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )

    return chunks


# Example Usage (for testing this module directly)
if __name__ == "__main__":
    from app.core.logging_config import setup_logging

    setup_logging()
    # Ensure tree-sitter-languages is installed for this example to work easily
    # pip install tree-sitter-languages
    logger.info("Attempting to load Python language...")
    lang = get_python_language()
    if not lang:
        logger.error("Exiting due to language loading failure.")
        exit(1)
    logger.info("Python language loaded successfully.")

    sample_code = """
# This is a comment
class MyClass:
    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value

def my_function(a, b):
    # A simple function
    return a + b

async def my_async_function():
    pass
    """
    sample_file_path = "example.py"
    logger.info(f"\nParsing sample code from '{sample_file_path}':")
    extracted_chunks = parse_and_extract_chunks(sample_file_path, sample_code)

    if extracted_chunks:
        logger.info(f"\nFound {len(extracted_chunks)} chunks:")
        for i, chunk in enumerate(extracted_chunks):
            logger.info(f"--- Chunk {i + 1} ---")
            logger.info(f"  ID: {chunk['id']}")
            logger.info(f"  Name: {chunk['chunk_name']}")
            logger.info(f"  Type: {chunk['type']}")
            logger.info(f"  Lines: {chunk['start_line']}-{chunk['end_line']}")
            snippet_text = chunk["code"][:50].replace("\n", " ")
            logger.info(f"  Code Snippet (first 50 chars): {snippet_text}...")
    else:
        logger.info("No chunks extracted or parsing failed.")

    # Test with a potentially problematic file (e.g., syntax error)
    error_code = """def func_with_syntax_error(:
        pass"""
    error_file_path = "error.py"
    logger.info(f"\nParsing sample code with syntax error from '{error_file_path}':")
    # Tree-sitter is robust and will often produce a partial AST with error nodes.
    # Our current chunking logic might still find valid preceding chunks or none.
    error_chunks = parse_and_extract_chunks(error_file_path, error_code)
    if error_chunks:
        logger.info(f"Found {len(error_chunks)} chunks despite errors.")
    else:
        logger.info(
            "No chunks extracted from file with errors, or parsing failed more severely."
        )
