import os
import shutil

from git import Repo, GitCommandError


def clone_or_pull_repository(repo_url: str, local_path: str) -> Repo | None:
    """
    Clones a repository if it doesn't exist locally, or pulls the latest changes
    if it already exists.

    Args:
        repo_url: The URL of the Git repository.
        local_path: The local directory to clone into or pull from.

    Returns:
        The GitPython Repo object if successful, None otherwise.
    """
    try:
        if os.path.exists(local_path):
            # Check if it's a valid git repo
            try:
                repo = Repo(local_path)
                print(f"Repository already exists at {local_path}. Pulling latest changes...")
                origin = repo.remotes.origin
                origin.pull()
                print("Successfully pulled latest changes.")
                return repo
            except GitCommandError as e:
                print(f"Directory {local_path} exists but is not a valid Git repository or pull failed: {e}")
                print("Consider removing the directory and trying again.")
                return None
            except Exception as e: # Catch other potential Repo() constructor errors
                print(f"Error accessing existing repository at {local_path}: {e}")
                print("Consider removing the directory and trying again.")
                return None
        else:
            print(f"Cloning repository {repo_url} to {local_path}...")
            repo = Repo.clone_from(repo_url, local_path)
            print("Successfully cloned repository.")
            return repo
    except GitCommandError as e:
        print(f"Git command error during clone/pull: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


# Example usage (optional, for testing this module directly)
if __name__ == "__main__":
    test_repo_url = "https://github.com/gitpython-developers/GitPython.git" # A public repo for testing
    test_local_path = "./temp_repo_clone"

    print("--- Test Case 1: Initial Clone ---")
    repo_instance = clone_or_pull_repository(test_repo_url, test_local_path)
    if repo_instance:
        print(f"Active branch: {repo_instance.active_branch}")

    print("\n--- Test Case 2: Pulling updates (should be no new changes if run immediately) ---")
    repo_instance_updated = clone_or_pull_repository(test_repo_url, test_local_path)
    if repo_instance_updated:
        print(f"Active branch: {repo_instance_updated.active_branch}")

    # Clean up the test directory
    if os.path.exists(test_local_path):
        print(f"\nCleaning up test directory: {test_local_path}")
        shutil.rmtree(test_local_path)
