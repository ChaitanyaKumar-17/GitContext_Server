"""
read_file.py
~~~~~~~~~~~~
Tool: read_file

Fetches the raw contents of a single file from a GitHub repository.

Safety guardrail: if the file exceeds MAX_FILE_SIZE_BYTES (30 KB), the tool
refuses to return the content and instead returns a structured message
suggesting search_code as an alternative — preventing context-window flooding.
"""

import logging
from typing import Any

from server.github_client import github_get, github_get_raw

log = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 30 * 1024  # 30 KB


async def read_file(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
) -> dict[str, Any]:
    """
    Return the raw text content of a file in `owner/repo`.

    Args:
        owner: GitHub repository owner.
        repo:  Repository name.
        path:  Path to the file within the repo (e.g. "src/main.py").
        ref:   Git ref (branch, tag, or commit SHA). Defaults to "main".

    Returns a dict with:
        - "path":    the requested file path
        - "ref":     the resolved ref
        - "size":    file size in bytes
        - "content": raw file text
    Or an error dict with "error" key, including the special case:
        {"error": "file_too_large", "size": <bytes>, "max": <bytes>,
         "suggestion": "Use search_code to locate specific sections."}
    """
    log.info(
        "read_file owner=%s repo=%s path=%r ref=%s",
        owner,
        repo,
        path,
        ref,
    )

    # First fetch metadata to check file size before downloading content
    meta = await github_get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})

    if "error" in meta:
        return meta

    # contents API returns a list for directories
    if isinstance(meta, list):
        return {
            "error": "is_directory",
            "message": f"'{path}' is a directory. Use get_repo_structure to list its contents.",
        }

    file_size = meta.get("size", 0)

    if file_size > MAX_FILE_SIZE_BYTES:
        log.warning(
            "read_file rejected: file too large size=%d path=%s", file_size, path
        )
        return {
            "error": "file_too_large",
            "path": path,
            "size": file_size,
            "max": MAX_FILE_SIZE_BYTES,
            "suggestion": (
                "File exceeds the 30 KB limit. "
                "Use search_code to locate specific sections instead."
            ),
        }

    # Fetch raw content
    raw = await github_get_raw(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})

    if isinstance(raw, dict) and "error" in raw:
        return raw

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "error": "binary_file",
            "path": path,
            "message": "File appears to be binary and cannot be returned as text.",
        }

    return {
        "owner": owner,
        "repo": repo,
        "path": path,
        "ref": ref,
        "size": file_size,
        "content": content,
    }
