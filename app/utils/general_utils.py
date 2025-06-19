from typing import Any


def repo_url_to_table_name(url: Any) -> str:
    repo_name = "/" .join(url.split("/")[-2:]).replace(".git", "")
    table_name = repo_name.replace("/", "_")
    return table_name
