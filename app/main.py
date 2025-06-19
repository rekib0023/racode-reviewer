import os

# Set tokenizers parallelism to avoid deadlocks with forked processes
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.chat_models import ChatOllama

from app.common.webhook_utils import extract_push_event_info, parse_webhook_payload
from app.diff_parser import FileDiff, parse_diff
from app.incremental_indexer import incremental_index_repository
from app.indexer import index_repository
from app.prompts import CODE_REVIEW_PROMPT_TEMPLATE
from app.rag_retriever import retrieve_relevant_code_chunks

from .auth import get_installation_access_token
from .github_client import fetch_pr_diff, post_review

load_dotenv()

# --- FastAPI App Initialization ---
app = FastAPI(title="Code Reviewer API")


# --- AI Model Initialization ---
# Workaround for Pydantic v2 warning in LangChain where a field name
# conflicts with a protected namespace.
class SafeChatOllama(ChatOllama):
    """A ChatOllama subclass that disables Pydantic's protected namespaces."""

    model_config = {"protected_namespaces": ()}


try:
    llm = SafeChatOllama(model="qwen2.5-coder:7b")
    print("Successfully connected to Ollama model.")
except Exception as e:
    print(f"Failed to connect to Ollama. Please ensure Ollama is running. Error: {e}")
    llm = None

# --- Helper Functions ---


async def generate_review_for_file(
    chain, file_diff: FileDiff, repo_url: str
) -> List[Dict[str, Any]]:
    """Generates review comments for a single file diff using RAG."""
    print(f"Generating review for file: {file_diff.path}")
    try:
        # 1. Retrieve context using RAG
        codebase_context = retrieve_relevant_code_chunks(
            repo_url=repo_url, file_path=file_diff.path, diff_content=file_diff.content
        )

        # 2. Invoke the LLM with the diff and context
        review_json = await chain.ainvoke(
            {
                "code_diff": file_diff.content,
                "codebase_context": codebase_context,
                "external_context": "Not provided.",
            }
        )

        if review_json:
            print(f"Received {len(review_json)} review comments for {file_diff.path}.")
            return review_json
        else:
            print(f"No review comments generated for {file_diff.path}.")
            return []

    except Exception as e:
        print(f"Error generating review for {file_diff.path}: {e}")
        return []


async def process_installation_event(full_name: str):
    """Process an installation event by triggering the incremental indexing pipeline."""
    print(f"Processing installation event for repo: {full_name}")
    index_repository(f"https://github.com/{full_name}.git")


async def process_push_event(push_info: Dict[str, str]):
    """Process a push event by triggering the incremental indexing pipeline."""
    print(f"Processing push event for repository: {push_info['repo_name']}")
    incremental_index_repository(
        push_info["repo_url"], push_info["before_commit"], push_info["after_commit"]
    )


async def handle_pull_request_event(payload: Dict[str, Any]):
    """
    Handles the full pipeline for a pull request event:
    - Fetches the diff
    - For each file, retrieves RAG context and generates AI review
    - Posts all comments in a single review to GitHub
    """
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        print("Error: Installation ID missing.")
        return

    try:
        token = get_installation_access_token(installation_id)
        pull_request = payload.get("pull_request", {})
        repo_info = payload.get("repository", {})
        owner = repo_info.get("owner", {}).get("login")
        repo_name = repo_info.get("name")
        repo_url = repo_info.get("clone_url")
        pull_number = pull_request.get("number")

        if not all([owner, repo_name, repo_url, pull_number]):
            print("Error: Missing PR details in payload.")
            return

        diff_content = fetch_pr_diff(token, owner, repo_name, pull_number)
        if not diff_content:
            print(f"Failed to fetch diff for PR #{pull_number}.")
            return

        print(f"Successfully fetched diff for PR #{pull_number}. Parsing diff...")
        file_diffs = parse_diff(diff_content)
        print(f"Parsed diff into {len(file_diffs)} file(s).")

        if not llm:
            print("Error: LLM is not available. Cannot process review.")
            return

        # Create the LangChain chain
        prompt = ChatPromptTemplate.from_template(CODE_REVIEW_PROMPT_TEMPLATE)
        chain = prompt | llm | JsonOutputParser()

        all_review_comments = []

        for file_diff in file_diffs:
            review_comments = await generate_review_for_file(chain, file_diff, repo_url)

            for comment in review_comments:
                line_number = comment.get("line_number")
                comment_text = comment.get("comment")

                # Map the line number to its position in the diff
                position = file_diff.line_mapping.get(line_number)

                if position and comment_text:
                    all_review_comments.append(
                        {
                            "path": file_diff.path,
                            "body": comment_text,
                            "position": position,
                        }
                    )
                else:
                    print(
                        f"Warning: Could not map line {line_number} for {file_diff.path}. Comment will be skipped."
                    )

        if all_review_comments:
            print(
                f"Submitting a single review with {len(all_review_comments)} comments."
            )
            post_review(token, owner, repo_name, pull_number, all_review_comments)
        else:
            print("No actionable comments generated. No review will be posted.")

    except Exception as e:
        print(f"An error occurred in the webhook handler: {e}")


@app.post("/api/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receives and processes webhook events from GitHub."""
    payload = await parse_webhook_payload(request)
    event = request.headers.get("X-GitHub-Event")

    match event:
        case "installation":
            installation_id = payload.get("installation", {}).get("id")
            if not installation_id:
                raise HTTPException(status_code=400, detail="Installation ID missing")
            repositories = payload.get("repositories", [])
            for repo in repositories:
                background_tasks.add_task(process_installation_event, repo["full_name"])
            return {
                "status": "accepted",
                "message": "Installation event accepted for processing.",
            }
        case "push":
            push_info = extract_push_event_info(payload)
            if not push_info:
                raise HTTPException(
                    status_code=400, detail="Invalid push event payload"
                )
            background_tasks.add_task(process_push_event, push_info)
            return {
                "status": "accepted",
                "message": "Push event accepted for indexing.",
            }

        case "pull_request":
            action = payload.get("action")
            if action in ["opened", "reopened", "synchronize"]:
                background_tasks.add_task(handle_pull_request_event, payload)
                return {
                    "status": "accepted",
                    "message": f"PR event '{action}' accepted for review.",
                }
            return {
                "status": "ignored",
                "message": f"PR action '{action}' not processed.",
            }

        case _:
            return {"status": "ignored", "message": f"Event '{event}' not processed."}


if __name__ == "__main__":
    import uvicorn

    print("Starting Code Reviewer API server...")
    print("Webhook endpoint available at: /api/webhook")
    print("Health check endpoint available at: /health")
    uvicorn.run(app, host="0.0.0.0", port=8000)
