<div align="center">
  <h1>🤖 RACode Reviewer</h1>
  <p>
    <strong>Retrieval-Augmented AI-Powered Code Review Assistant</strong>
  </p>
  <p>
    <a href="#features">Features</a> • 
    <a href="#architecture">Architecture</a> • 
    <a href="#quick-start">Quick Start</a> • 
    <a href="#usage">Usage</a> • 
    <a href="#design-patterns">Design Patterns</a> • 
    <a href="#contributing">Contributing</a>
  </p>
  <p>
    <a href="https://github.com/rekib0023/racode-reviewer/actions">
      <img src="https://img.shields.io/github/workflow/status/rekib0023/racode-reviewer/CI" alt="Build Status">
    </a>
    <a href="https://github.com/psf/black">
      <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code Style: Black">
    </a>
    <a href="https://github.com/rekib0023/racode-reviewer/blob/main/LICENSE">
      <img src="https://img.shields.io/github/license/rekib0023/racode-reviewer" alt="License">
    </a>
    <a href="https://github.com/rekib0023/racode-reviewer/issues">
      <img src="https://img.shields.io/github/issues/rekib0023/racode-reviewer" alt="Issues">
    </a>
  </p>
</div>

## 📖 Overview

RACode Reviewer is a production-grade AI-powered code review system that leverages Retrieval-Augmented Generation (RAG) to provide context-aware, intelligent code reviews. By combining traditional static analysis with modern AI techniques, it delivers high-quality, insightful feedback that improves code quality while saving developer time.

Built with modularity and extensibility in mind, this system employs robust design patterns, comprehensive error handling, and professional logging practices to ensure reliability and maintainability in real-world development environments.

## 🚀 Features

- **AI-Powered Code Reviews**: Leverages state-of-the-art language models for insightful code analysis that goes beyond simple linting
- **Retrieval-Augmented Generation (RAG)**: Uses vector embeddings to ensure the AI has full context of your codebase when providing reviews
- **GitHub Integration**: Seamlessly integrates with GitHub repositories and pull requests via webhooks
- **Incremental Indexing**: Smart repository indexing system that only processes changed files for optimal performance
- **Multi-language Support**: Built-in support for multiple programming languages with language-specific review insights
- **Error Resilience**: Comprehensive error handling with custom exception hierarchy for robust operation
- **Vector Database**: Efficient storage and retrieval of code embeddings using LanceDB
- **Configurable Settings**: Easily configurable via environment variables with sensible defaults
- **Comprehensive Logging**: Professional logging system with appropriate log levels and contextual information

## 🌐 Architecture

RACode Reviewer is built on a modular architecture designed for scalability and maintainability:

### Core Components

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   GitHub API    │◄────►│   FastAPI App   │◄────►│   LLM Service   │
└─────────────────┘      └────────┬────────┘      └────────┬────────┘
                                  │                         │
                         ┌────────┴────────┐      ┌────────┴────────┐
                         │  GitHub Service │      │ Vector Database │
                         └────────┬────────┘      └────────┬────────┘
                                  │                         │
                         ┌────────┴────────┐      ┌────────┴────────┐
                         │Incremental Index│◄────►│  Embedding Gen  │
                         └─────────────────┘      └─────────────────┘
```

### System Flow

1. **GitHub Events**: Webhooks deliver repository events (pushes, pull requests)
2. **Incremental Indexing**: Changed code is identified, parsed, and vectorized
3. **Vector Storage**: Code embeddings are stored in LanceDB for efficient retrieval
4. **Review Generation**: When pull requests arrive, relevant code context is retrieved
5. **AI Processing**: Language model generates detailed code reviews with domain awareness
6. **Feedback Delivery**: Reviews are posted as comments on pull requests

## 🏃 Quick Start

### Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai/) (for local LLM inference)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/rekib0023/racode-reviewer.git
cd racode-reviewer

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit the .env file with your configuration
```

### Running the Service

```bash
# Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/docs` for the interactive API documentation.

## 💻 Design Patterns

RACode Reviewer implements several design patterns to ensure code quality and maintainability:

### Singleton Pattern

Used in `core/config.py` to ensure a single, global configuration instance is maintained throughout the application lifetime.

```python
def get_settings() -> Settings:
    """Returns the settings instance, creating it if necessary."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

### Factory Pattern

Implemented in `indexing/embedding_generator.py` to dynamically create appropriate embedding model instances based on configuration.

```python
def get_embedding_model(model_name: str) -> SentenceTransformerEmbeddings:
    """Factory function to get embedding model instance."""
    # Dynamic model initialization based on configuration
```

### Repository Pattern

Used for data access abstraction in the vector database interactions, separating business logic from data storage concerns.

### Exception Hierarchy

Custom exception hierarchy in `core/exceptions.py` for domain-specific error handling:

```
CodeReviewerException
├── RepositoryException
│   ├── RepositoryCloneError
│   └── RepositoryIndexingError
├── GitHubServiceException
│   ├── InvalidWebhookPayloadError
│   └── WebhookProcessingError
├── LLMServiceException
│   └── ReviewGenerationError
├── WebhookNotificationError
└── VectorDBError
```

## 💬 Usage

### GitHub Integration

1. **Create a GitHub App**:
   - Go to GitHub Developer Settings > GitHub Apps > New GitHub App
   - Set the webhook URL to your deployed instance (`https://your-server/api/github/webhook`)
   - Required permissions: Repository (Read), Pull requests (Read & Write)
   - Subscribe to webhook events: Pull request, Push
   - Generate and download a private key

2. **Configure Environment Variables**:
   ```env
   # GitHub App Configuration
   GITHUB_APP_ID=your_app_id
   GITHUB_APP_PRIVATE_KEY="path/to/private-key.pem"
   GITHUB_WEBHOOK_SECRET=your_webhook_secret
   ```

3. **Install the GitHub App**:
   - Install the app on repositories you want to analyze
   - The app will automatically begin processing push events and pull requests

### Using the API

The following endpoints are available:

- `GET /api/health` - Check service health
- `POST /api/github/webhook` - GitHub webhook endpoint
- `POST /api/repos/index` - Manually trigger repository indexing
- `GET /api/repos/{repo_name}/stats` - Get repository indexing statistics

## 👨‍💻 Contributing

Contributions are welcome! Please follow these steps to contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide for Python code
- Write unit tests for new features
- Document code with docstrings
- Update README.md with any necessary information

## 💡 Roadmap

- [ ] Add support for more code hosting platforms (GitLab, Bitbucket)
- [ ] Implement support for additional LLM providers
- [ ] Add customizable review rules and policies
- [ ] Develop a web UI for configuration and monitoring
- [ ] Improve support for non-Python languages

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) for AI framework components
- [FastAPI](https://github.com/tiangolo/fastapi) for API framework
- [LanceDB](https://github.com/lancedb/lancedb) for vector database
- [SentenceTransformers](https://github.com/UKPLab/sentence-transformers) for embedding models
GITHUB_PRIVATE_KEY_PATH=path/to/private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Database Configuration
LANCE_DB_PATH=./lancedb_data
```

## 🛠️ Development

### Running Tests

```bash
# Install test dependencies
pip install -e ".[test]"

# Run tests
pytest
```

### Code Style

This project uses:
- [Black](https://github.com/psf/black) for code formatting
- [isort](https://github.com/PyCQA/isort) for import sorting
- [mypy](https://mypy.readthedocs.io/) for static type checking

```bash
# Format code
black .

# Sort imports
isort .

# Type checking
mypy .
```

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details on how to submit pull requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai/) for the local LLM framework
- [LanceDB](https://lancedb.com/) for vector database
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [LangChain](https://python.langchain.com/) for LLM orchestration
```bash
uv run python -m app.webhook_handler
```

This starts a FastAPI server that listens for GitHub webhook events on `/webhook/github`. When a push event is received, it:

1. Validates the webhook signature using `GITHUB_WEBHOOK_SECRET`
2. Extracts repository URL and commit information
3. Triggers incremental indexing in the background

### Webhook Setup

1. Add `GITHUB_WEBHOOK_SECRET` to your `.env` file
2. Deploy the webhook handler or expose it via a tunnel (e.g., ngrok)
3. Configure a webhook in your GitHub repository settings:
   - Payload URL: `https://your-server/webhook/github`
   - Content type: `application/json`
   - Secret: The same value as `GITHUB_WEBHOOK_SECRET`
   - Events: Select at least the `push` event

## Future Enhancements

- Support for additional programming languages beyond Python
- Code review generation using LLMs
- Pull request comment generation
- Performance optimizations for very large codebases
