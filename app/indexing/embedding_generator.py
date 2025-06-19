import logging
import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings

_MODEL_INSTANCE: Optional[SentenceTransformer] = None
logger = logging.getLogger("app")


def initialize_embedding_model(
    model_name: str = settings.EMBEDDING_MODEL_NAME,  # Default from settings
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
            # Use SENTENCE_TRANSFORMERS_HOME from settings if provided
            cache_folder = settings.SENTENCE_TRANSFORMERS_HOME
            _MODEL_INSTANCE = SentenceTransformer(model_name, cache_folder=cache_folder)
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
    # Setup basic logging for the script execution
    from app.core.logging_config import setup_logging

    setup_logging()
    logger.info("Running embedding_generator.py directly.")

    # Ensure sentence-transformers is installed: pip install sentence-transformers
    logger.info(f"Using EMBEDDING_MODEL_NAME: {settings.EMBEDDING_MODEL_NAME}")
    if settings.SENTENCE_TRANSFORMERS_HOME:
        logger.info(
            f"Using SENTENCE_TRANSFORMERS_HOME: {settings.SENTENCE_TRANSFORMERS_HOME}"
        )
    else:
        logger.info("SENTENCE_TRANSFORMERS_HOME not set, using default cache location.")

    # Example: Initialize the model using settings
    logger.info("--- Testing Embedding Model Initialization ---")
    try:
        # initialize_embedding_model will use settings.EMBEDDING_MODEL_NAME by default
        model = initialize_embedding_model()
        logger.info(
            f"Model ({settings.EMBEDDING_MODEL_NAME}) initialized successfully."
        )
    except Exception as e:
        logger.error(f"Failed to initialize model from settings: {e}")
        # exit(1)

    logger.info("--- Testing Embedding Generation ---")
    test_sentences = [
        "This is an example sentence.",
        "Each sentence is converted to a vector.",
    ]

    if _MODEL_INSTANCE:  # Check if model was initialized
        try:
            embeddings = model.encode(test_sentences, convert_to_numpy=True)
            if embeddings is not None:
                logger.info(
                    f"Generated embeddings for {len(test_sentences)} sentences."
                )
                logger.info(f"Shape of first embedding: {embeddings[0].shape}")
            else:
                logger.warning("Embedding generation returned None for list.")

            single_embedding = model.encode(test_sentences[0], convert_to_numpy=True)
            if single_embedding is not None:
                logger.info("Generated embedding for a single sentence.")
                logger.info(f"Shape of single embedding: {single_embedding.shape}")
            else:
                logger.warning("Single embedding generation returned None.")

        except Exception as e:
            logger.error(f"Error during embedding generation test: {e}")
    else:
        logger.warning(
            "Skipping embedding generation test as model failed to initialize."
        )
        logger.error("Skipping embedding tests as model initialization failed.")
