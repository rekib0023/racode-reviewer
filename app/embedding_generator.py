import logging
import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from typing import Optional  # Removed List

import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_INSTANCE: Optional[SentenceTransformer] = None
logger = logging.getLogger("app")


def initialize_embedding_model(
    model_name: str = "all-MiniLM-L6-v2",
) -> SentenceTransformer:
    """
    Initializes and returns a SentenceTransformer model.
    Caches the model instance globally to avoid reloading.

    Args:
        model_name: The name of the sentence-transformer model to load.
                    Defaults to "all-MiniLM-L6-v2".

    Returns:
        The loaded SentenceTransformer model.

    Raises:
        Exception: If the model fails to load.
    """
    global _MODEL_INSTANCE
    if _MODEL_INSTANCE is None:
        logger.info(f"Initializing embedding model: {model_name}...")
        try:
            # You can specify a cache folder for models if needed
            # cache_folder = os.getenv("SENTENCE_TRANSFORMERS_HOME")
            _MODEL_INSTANCE = SentenceTransformer(
                model_name
            )  # , cache_folder=cache_folder)
            logger.info(f"Embedding model '{model_name}' loaded successfully.")
        except Exception as e:
            logger.error(
                f"Error loading sentence transformer model '{model_name}': {e}"
            )
            # Potentially raise a custom exception or handle more gracefully
            raise
    return _MODEL_INSTANCE


def get_embedding(
    code_chunk: str, model: Optional[SentenceTransformer] = None
) -> Optional[np.ndarray]:
    """
    Generates a vector embedding for a given code chunk string.

    Args:
        code_chunk: The string of code to embed.
        model: The pre-loaded SentenceTransformer model. If None, it will try to initialize it.

    Returns:
        A numpy array representing the embedding, or None if an error occurs.
    """
    if model is None:
        try:
            # Attempt to use the default model name from environment or a fallback
            default_model_name = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
            model = initialize_embedding_model(default_model_name)
        except Exception as e:
            logger.error(f"Failed to initialize embedding model for get_embedding: {e}")
            return None

    if not code_chunk or not isinstance(code_chunk, str):
        logger.error("Error: Code chunk is empty or not a string.")
        return None

    try:
        embedding = model.encode(code_chunk, convert_to_numpy=True)
        return embedding
    except Exception as e:
        logger.error(f"Error generating embedding for chunk: {e}")
        return None


# Example Usage (for testing this module directly)
if __name__ == "__main__":
    # Ensure sentence-transformers is installed: pip install sentence-transformers
    logger.info("--- Testing Embedding Generation ---")

    # Test model initialization
    try:
        test_model_name = "all-MiniLM-L6-v2"  # A common, relatively small model
        logger.info(f"Attempting to initialize model: {test_model_name}")
        transformer_model = initialize_embedding_model(test_model_name)
    except Exception as e:
        logger.error(f"Failed to initialize model for testing: {e}")
        transformer_model = None

    if transformer_model:
        logger.info(
            f"Model '{test_model_name}' initialized. Embedding dimension: {transformer_model.get_sentence_embedding_dimension()}"
        )

        sample_code_chunks = [
            "def hello_world():\n    print('Hello, world!')",
            "class Calculator:\n    def add(self, x, y):\n        return x + y",
            "import numpy as np",
        ]

        for i, chunk in enumerate(sample_code_chunks):
            logger.info(f"\n--- Embedding Chunk {i + 1} ---")
            logger.info(f"Code: {chunk[:50].replace('\n', ' ')}...")
            embedding_vector = get_embedding(chunk, transformer_model)
            if embedding_vector is not None:
                logger.info(f"Embedding (first 5 values): {embedding_vector[:5]}")
                logger.info(f"Embedding shape: {embedding_vector.shape}")
            else:
                logger.error("Failed to generate embedding.")

        # Test with an empty chunk
        logger.info("\n--- Embedding Empty Chunk ---")
        empty_embedding = get_embedding("", transformer_model)
        if empty_embedding is None:
            logger.info("Correctly handled empty chunk (returned None).")
        else:
            logger.warning(
                f"Unexpectedly got embedding for empty chunk: {empty_embedding}"
            )
    else:
        logger.error("Skipping embedding tests as model initialization failed.")
