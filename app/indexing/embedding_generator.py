"""
Embedding Generator module implementing the Factory pattern for model management.

This module provides a factory for creating and managing embedding model instances,
with support for different model backends and configuration options. It abstracts
the complexity of model initialization and caching.
"""

import os
from abc import ABC, abstractmethod
from enum import Enum
from functools import lru_cache
from typing import Dict, Optional, Type, Union

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ModelType(str, Enum):
    """
    Enumeration of supported embedding model types.

    This allows for easy extension to support additional model types in the future.
    """

    SENTENCE_TRANSFORMER = "sentence_transformer"
    # Future model types can be added here (e.g., OPENAI, HUGGINGFACE, etc.)


class EmbeddingModel(ABC):
    """
    Abstract base class for embedding models.

    This class defines the interface that all embedding model implementations must follow.
    """

    @abstractmethod
    def encode(self, text: Union[str, list[str]], **kwargs) -> np.ndarray:
        """
        Generate embeddings for the provided text.

        Args:
            text: Text to encode, can be a single string or a list of strings
            **kwargs: Additional arguments for specific model implementations

        Returns:
            numpy.ndarray: The generated embedding vector(s)
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors produced by this model.

        Returns:
            int: The dimension of the embedding vectors
        """
        pass


class SentenceTransformerModel(EmbeddingModel):
    """
    Embedding model implementation using SentenceTransformer.

    This class wraps the SentenceTransformer model to conform to our EmbeddingModel interface.
    """

    def __init__(self, model_name: str, cache_folder: Optional[str] = None):
        """
        Initialize the SentenceTransformer model.

        Args:
            model_name: Name of the sentence-transformer model to load
            cache_folder: Optional folder to cache models
        """
        logger.info(f"Initializing SentenceTransformer model: {model_name}")
        try:
            self.model = SentenceTransformer(model_name, cache_folder=cache_folder)
            logger.info(f"SentenceTransformer model '{model_name}' loaded successfully")
        except Exception as e:
            logger.error(f"Error loading SentenceTransformer model '{model_name}': {e}")
            raise

    def encode(self, text: Union[str, list[str]], **kwargs) -> np.ndarray:
        """
        Generate embeddings using SentenceTransformer.

        Args:
            text: Text to encode, can be a single string or a list of strings
            **kwargs: Additional arguments for SentenceTransformer.encode

        Returns:
            numpy.ndarray: The generated embedding vector(s)
        """
        convert_to_numpy = kwargs.get("convert_to_numpy", True)
        return self.model.encode(text, convert_to_numpy=convert_to_numpy)

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension of the SentenceTransformer model.

        Returns:
            int: The embedding dimension
        """
        return self.model.get_sentence_embedding_dimension()


class EmbeddingModelFactory:
    """
    Factory class for creating and managing embedding model instances.

    This class implements the Factory pattern to create different types of embedding models
    while abstracting away the complexity of model initialization and caching.
    """

    _model_registry: Dict[str, Type[EmbeddingModel]] = {
        ModelType.SENTENCE_TRANSFORMER: SentenceTransformerModel,
    }

    _instances: Dict[str, EmbeddingModel] = {}

    @classmethod
    def register_model_type(
        cls, model_type: str, model_class: Type[EmbeddingModel]
    ) -> None:
        """
        Register a new model type with the factory.

        Args:
            model_type: String identifier for the model type
            model_class: The model implementation class
        """
        cls._model_registry[model_type] = model_class
        logger.info(f"Registered model type '{model_type}' with factory")

    @classmethod
    def get_model(
        cls,
        model_name: str = settings.EMBEDDING_MODEL_NAME,
        model_type: str = ModelType.SENTENCE_TRANSFORMER,
        **kwargs,
    ) -> EmbeddingModel:
        """
        Get an instance of an embedding model, creating it if it doesn't exist.

        Args:
            model_name: Name of the model to initialize
            model_type: Type of model to initialize
            **kwargs: Additional arguments for model initialization

        Returns:
            EmbeddingModel: The requested model instance

        Raises:
            ValueError: If the model type is not supported
        """
        model_key = f"{model_type}:{model_name}"

        if model_key not in cls._instances:
            logger.info(f"Creating new model instance for '{model_key}'")

            if model_type not in cls._model_registry:
                raise ValueError(f"Unsupported model type: {model_type}")

            model_class = cls._model_registry[model_type]

            # Handle specific initialization for different model types
            if model_type == ModelType.SENTENCE_TRANSFORMER:
                cache_folder = settings.SENTENCE_TRANSFORMERS_HOME
                cls._instances[model_key] = model_class(model_name, cache_folder)
            else:
                cls._instances[model_key] = model_class(model_name, **kwargs)

        return cls._instances[model_key]

    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear the cache of model instances.
        """
        cls._instances.clear()
        logger.info("Cleared model instance cache")


@lru_cache()
def get_embedding_model() -> EmbeddingModel:
    """
    Get the default embedding model instance.

    This function implements the Singleton pattern using lru_cache to ensure
    that only one instance of the embedding model is created.

    Returns:
        EmbeddingModel: The singleton instance of the embedding model
    """
    return EmbeddingModelFactory.get_model()


def get_embedding(
    code_chunk: str, model: Optional[EmbeddingModel] = None
) -> Optional[np.ndarray]:
    """
    Generates a vector embedding for a given code chunk string.

    Args:
        code_chunk: The string of code to embed.
        model: The pre-loaded EmbeddingModel. If None, it will use the default model.

    Returns:
        A numpy array representing the embedding, or None if an error occurs.
    """
    if model is None:
        try:
            model = get_embedding_model()
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            return None

    if not code_chunk or not isinstance(code_chunk, str):
        logger.error("Error: Code chunk is empty or not a string")
        return None

    try:
        embedding = model.encode(code_chunk)
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

    # Example: Initialize the model using the Factory
    logger.info("--- Testing Embedding Model Factory ---")
    try:
        # Get a model using the factory
        model = get_embedding_model()
        logger.info(
            f"Model ({settings.EMBEDDING_MODEL_NAME}) initialized successfully using Factory."
        )
        logger.info(f"Model embedding dimension: {model.get_embedding_dimension()}")
    except Exception as e:
        logger.error(f"Failed to initialize model from factory: {e}")
        exit(1)

    # Test registering a new model type (just for demonstration)
    logger.info("--- Testing Model Type Registration ---")
    # This would normally be a different model implementation
    # EmbeddingModelFactory.register_model_type("custom_model", CustomModelClass)
    logger.info(
        f"Available model types: {list(EmbeddingModelFactory._model_registry.keys())}"
    )

    logger.info("--- Testing Embedding Generation ---")
    test_sentences = [
        "This is an example sentence.",
        "Each sentence is converted to a vector.",
    ]

    try:
        # Generate embeddings for multiple sentences
        embeddings = model.encode(test_sentences)
        if isinstance(embeddings, np.ndarray):
            logger.info(f"Generated embeddings for {len(test_sentences)} sentences.")
            logger.info(f"Shape of embeddings: {embeddings.shape}")
            logger.info(
                f"Shape of first embedding: {embeddings[0].shape if len(embeddings.shape) > 1 else embeddings.shape}"
            )
        else:
            logger.warning("Embedding generation returned non-numpy array result.")

        # Generate embedding for single sentence
        single_embedding = model.encode(test_sentences[0])
        if isinstance(single_embedding, np.ndarray):
            logger.info("Generated embedding for a single sentence.")
            logger.info(f"Shape of single embedding: {single_embedding.shape}")
        else:
            logger.warning(
                "Single embedding generation returned non-numpy array result."
            )

    except Exception as e:
        logger.error(f"Error during embedding generation test: {e}")

    # Test clearing cache
    logger.info("--- Testing Cache Management ---")
    logger.info(
        f"Number of models in cache before clearing: {len(EmbeddingModelFactory._instances)}"
    )
    EmbeddingModelFactory.clear_cache()
    logger.info(
        f"Number of models in cache after clearing: {len(EmbeddingModelFactory._instances)}"
    )
