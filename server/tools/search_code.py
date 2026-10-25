"""
search_code.py
~~~~~~~~~~~~~~
Tool: search_code

Searches code across a GitHub repository using the GitHub Code Search API.
Returns matches with file path, line number (when available), and a snippet.

Note: GitHub Code Search requires authentication; unauthenticated calls are
severely rate-limited (or blocked). The github_client always sends GITHUB_TOKEN.
"""

import logging
from typing import Any

from server.github_client import github_get

log = logging.getLogger(__name__)

_MAX_RESULTS = 30  # cap to keep context window manageable


async def search_code(
    owner: str,
    repo: str,
    query: str,
    file_extension: str | None = None,
) -> dict[str, Any]:
    """
    Search for `query` in the source code of `owner/repo`.

    Args:
        owner:          GitHub repository owner.
        repo:           Repository name.
        query:          Search string (supports GitHub search qualifiers).
        file_extension: Optional file extension filter, e.g. "py", "ts".

    Returns a dict with:
        - "total_count": total number of matches GitHub found
        - "returned":    number of matches in this response (capped at 30)
        - "matches":     list of {"path", "url", "text_matches": [...]}
    Or an error dict with an "error" key.
    """
    log.info(
        "search_code owner=%s repo=%s query=%r extension=%s",
        owner,
        repo,
        query,
        file_extension,
    )

    q = f"{query} repo:{owner}/{repo}"
    if file_extension:
        ext = file_extension.lstrip(".")
        q += f" extension:{ext}"

    params: dict[str, Any] = {
        "q": q,
        "per_page": min(_MAX_RESULTS, 30),  # GitHub max per_page is 100 but we cap lower
    }

    # Request text-match metadata so we get snippets
    result = await github_get(
        "/search/code",
        params=params,
    )

    if "error" in result:
        return result

    items = result.get("items", [])
    matches = []
    for item in items:
        match_entry: dict[str, Any] = {
            "path": item.get("path"),
            "url": item.get("html_url"),
            "text_matches": [],
        }
        for tm in item.get("text_matches", []):
            match_entry["text_matches"].append(
                {
                    "fragment": tm.get("fragment", ""),
                    "matches": [
                        {"text": m.get("text"), "indices": m.get("indices")}
                        for m in tm.get("matches", [])
                    ],
                }
            )
        matches.append(match_entry)

    return {
        "owner": owner,
        "repo": repo,
        "query": query,
        "total_count": result.get("total_count", 0),
        "returned": len(matches),
        "matches": matches,
    }
