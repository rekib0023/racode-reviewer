# Code Reviewer

A GitHub App backend with Retrieval-Augmented Generation (RAG) capabilities for code analysis and review.

## Project Overview

This project implements a backend service for a GitHub App that can analyze code repositories using RAG techniques. The system:

1. Clones GitHub repositories
2. Parses code into meaningful chunks using Abstract Syntax Trees (AST)
3. Generates embeddings for code chunks
4. Stores code chunks and embeddings in a vector database
5. Provides semantic search capabilities for code understanding

## Core Components

### Repository Management

- `app/repo_manager.py`: Handles cloning and pulling repositories using GitPython

### Code Processing

- `app/code_parser.py`: Parses Python code into meaningful chunks (functions and classes) using tree-sitter
- `app/embedding_generator.py`: Generates embeddings for code chunks using sentence-transformers

### Vector Database

- `app/vector_store.py`: Manages LanceDB connections and tables for storing code chunks and embeddings

### Pipeline Orchestration

- `app/indexer.py`: Orchestrates the full pipeline of cloning, parsing, embedding, and indexing
- `app/query_engine.py`: Provides semantic search capabilities for querying indexed code

## Getting Started

### Prerequisites

- Python 3.12
- Dependencies listed in `pyproject.toml`

### Environment Setup

1. Clone this repository
2. Create a `.env` file based on `.env.example`
3. Install dependencies:
   ```bash
   uv pip sync pyproject.toml
   ```

### Indexing a Repository

To index a GitHub repository:

```bash
uv run python -m app.indexer
```

By default, this will index the sample repository specified in the script. To index a different repository, modify the `sample_repo_url` in `app/indexer.py`.

### Querying Indexed Code

To query the indexed code:

```bash
uv run python -m app.query_engine --query "How does the chat service work?"
```

Or for multiple queries:

```bash
uv run python -m app.query_engine --interactive
```

## Configuration

The following environment variables can be set in `.env`:

- `REPO_CLONE_DIR`: Directory for cloning repositories
- `LANCEDB_PATH`: Path to the LanceDB database
- `EMBEDDING_MODEL_NAME`: Name of the embedding model to use

## Future Enhancements

- Support for additional programming languages beyond Python
- Integration with GitHub webhooks for automatic indexing
- Code review generation using LLMs
- Pull request comment generation
