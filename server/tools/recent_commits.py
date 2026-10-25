"""
recent_commits.py
~~~~~~~~~~~~~~~~~
Tool: get_recent_commits

Returns recent commit log entries for a GitHub repository, optionally
filtered to a specific file/directory path — useful for "what changed here
recently?" questions.
"""

import logging
from typing import Any

from server.github_client import github_get

log = logging.getLogger(__name__)

_MAX_LIMIT = 50  # hard cap — prevents accidentally pulling hundreds of commits


async def get_recent_commits(
    owner: str,
    repo: str,
    limit: int = 10,
    path: str | None = None,
) -> dict[str, Any]:
    """
    Return recent commits for `owner/repo`, optionally scoped to `path`.

    Args:
        owner: GitHub repository owner.
        repo:  Repository name.
        limit: Number of commits to return (1–50, default 10).
        path:  Optional file or directory path to filter commits by.

    Returns a dict with:
        - "commits": list of {sha, author, email, date, message, url}
        - "count":   number of commits returned
        - "path":    the path filter used (None if not filtered)
    Or an error dict with "error" key.
    """
    log.info(
        "get_recent_commits owner=%s repo=%s limit=%d path=%s",
        owner,
        repo,
        limit,
        path,
    )

    limit = max(1, min(limit, _MAX_LIMIT))

    params: dict[str, Any] = {"per_page": limit}
    if path:
        params["path"] = path

    result = await github_get(f"/repos/{owner}/{repo}/commits", params=params)

    if "error" in result:
        return result

    # result is a list of commit objects
    if not isinstance(result, list):
        return {
            "error": "unexpected_response",
            "message": "GitHub returned an unexpected response format for commits.",
        }

    commits = []
    for item in result:
        commit = item.get("commit", {})
        author_info = commit.get("author", {})
        gh_author = item.get("author") or {}

        commits.append(
            {
                "sha": item.get("sha", "")[:12],  # short SHA — 12 chars is enough
                "full_sha": item.get("sha", ""),
                "author": author_info.get("name", "unknown"),
                "email": author_info.get("email", ""),
                "github_login": gh_author.get("login"),
                "date": author_info.get("date", ""),
                "message": commit.get("message", "").strip(),
                "url": item.get("html_url", ""),
            }
        )

    return {
        "owner": owner,
        "repo": repo,
        "path": path,
        "count": len(commits),
        "commits": commits,
    }
