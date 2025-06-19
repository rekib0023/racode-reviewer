<div align="center">
  <h1>🤖 Code Reviewer</h1>
  <p>
    <strong>AI-Powered Code Review Assistant</strong> | 
    <a href="#features">Features</a> • 
    <a href="#quick-start">Quick Start</a> • 
    <a href="#documentation">Documentation</a> • 
    <a href="#contributing">Contributing</a>
  </p>
  <p>
    <a href="https://github.com/yourusername/code-reviewer/actions">
      <img src="https://github.com/yourusername/code-reviewer/actions/workflows/tests.yml/badge.svg" alt="Build Status">
    </a>
    <a href="https://codecov.io/gh/yourusername/code-reviewer">
      <img src="https://codecov.io/gh/yourusername/code-reviewer/branch/main/graph/badge.svg" alt="Code Coverage">
    </a>
    <a href="https://pypi.org/project/code-reviewer/">
      <img src="https://img.shields.io/pypi/v/code-reviewer" alt="PyPI Version">
    </a>
    <a href="https://github.com/psf/black">
      <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code Style: Black">
    </a>
  </p>
</div>

## 🚀 Features

- **AI-Powered Code Reviews**: Leverage state-of-the-art language models for insightful code analysis
- **Retrieval-Augmented Generation (RAG)**: Context-aware code understanding using vector embeddings
- **GitHub Integration**: Seamless integration with GitHub repositories and pull requests
- **Incremental Indexing**: Smart updates to only process changed code
- **Multi-language Support**: Built-in support for multiple programming languages
- **Customizable Rules**: Define your own code review guidelines and standards

## 🏃 Quick Start

### Prerequisites

- Python 3.9+
- Ollama (for local LLM)
- Git
- [Docker](https://docs.docker.com/get-docker/) (optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/code-reviewer.git
cd code-reviewer

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit the .env file with your configuration
# See Configuration section for details
```

### Running the Service

```bash
# Start the FastAPI server
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for the interactive API documentation.

## 📚 Documentation

For detailed documentation, please see our [Technical Documentation](TECHNICAL_DOCS.md).

### Core Components

| Component | Description |
|-----------|-------------|
| **GitHub Service** | Handles GitHub API interactions and webhook events |
| **LLM Service** | Manages language model interactions and review generation |
| **Vector Store** | Stores and retrieves code embeddings using LanceDB |
| **Repository Manager** | Handles Git operations and repository management |

### Configuration

Create a `.env` file with the following variables:

```env
# Ollama Configuration
CHAT_MODEL_NAME=deepseek-coder:7b

# GitHub App Configuration
GITHUB_APP_ID=your_app_id
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
