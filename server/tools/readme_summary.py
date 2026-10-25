"""
readme_summary.py
~~~~~~~~~~~~~~~~~
Tool: summarize_readme

Fetches the raw README content for a GitHub repository.
The raw text is returned to the calling model to summarize — no second LLM
call is made inside this tool (avoids cost, complexity, and an extra API key).
"""

import logging
from typing import Any

from server.github_client import github_get_raw

log = logging.getLogger(__name__)

# GitHub tries these filenames in order; we mirror the same priority list
_README_CANDIDATES = [
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "readme.md",
    "Readme.md",
]


async def summarize_readme(owner: str, repo: str) -> dict[str, Any]:
    """
    Return the raw README content for `owner/repo`.

    The calling model is expected to summarize it. This tool deliberately
    avoids making a nested LLM call.

    Args:
        owner: GitHub repository owner.
        repo:  Repository name.

    Returns a dict with:
        - "path":    the README filename that was found
        - "content": raw README text
        - "size":    byte size of the README
    Or an error dict with "error" key.
    """
    log.info("summarize_readme owner=%s repo=%s", owner, repo)

    for candidate in _README_CANDIDATES:
        raw = await github_get_raw(f"/repos/{owner}/{repo}/contents/{candidate}")

        # Not found → try next candidate
        if isinstance(raw, dict) and raw.get("error") == "not_found":
            continue

        # Any other error → surface it immediately
        if isinstance(raw, dict) and "error" in raw:
            return raw

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("latin-1", errors="replace")

        return {
            "owner": owner,
            "repo": repo,
            "path": candidate,
            "size": len(raw),
            "content": content,
        }

    return {
        "error": "not_found",
        "message": f"No README file found in {owner}/{repo}.",
    }
