"""
repo_structure.py
~~~~~~~~~~~~~~~~~
Tool: get_repo_structure

Returns a depth-limited file/folder tree for a given path in a GitHub repository.
Uses the GitHub Trees API with recursive=1 and then prunes client-side to the
requested max_depth, avoiding multiple round-trips.
"""

import logging
from typing import Any

from server.github_client import github_get

log = logging.getLogger(__name__)

_MAX_ALLOWED_DEPTH = 5  # hard cap to prevent abuse


def _build_tree(
    items: list[dict],
    root_path: str,
    max_depth: int,
) -> list[dict]:
    """
    Filter the flat GitHub tree list to items under root_path,
    pruned to max_depth levels below that root.
    """
    root_prefix = (root_path.rstrip("/") + "/") if root_path else ""
    result = []

    for item in items:
        path: str = item.get("path", "")

        # Must be under the requested root
        if root_prefix and not path.startswith(root_prefix):
            continue

        relative = path[len(root_prefix):]
        depth = relative.count("/") + (0 if item["type"] == "blob" else 0)

        # Depth check: a path with N slashes is at depth N+1 relative to root
        if relative.count("/") >= max_depth:
            continue

        result.append(
            {
                "path": path,
                "type": item["type"],  # "blob" | "tree"
                "size": item.get("size"),  # bytes, only for blobs
            }
        )

    return result


async def get_repo_structure(
    owner: str,
    repo: str,
    path: str = "",
    max_depth: int = 2,
) -> dict[str, Any]:
    """
    Return the file/folder tree for `path` in `owner/repo`, limited to `max_depth`.

    Args:
        owner:     GitHub repository owner (user or org).
        repo:      Repository name.
        path:      Sub-directory to list (empty string = repo root).
        max_depth: How many directory levels to include (1–5, default 2).

    Returns a dict with:
        - "tree": list of {"path", "type", "size"} entries
        - "truncated": bool — True if GitHub truncated the tree (>100k entries)
    Or an error dict with an "error" key.
    """
    log.info(
        "get_repo_structure owner=%s repo=%s path=%r max_depth=%d",
        owner,
        repo,
        path,
        max_depth,
    )

    # Clamp max_depth
    max_depth = max(1, min(max_depth, _MAX_ALLOWED_DEPTH))

    # Resolve the default branch SHA so the Trees API can be called
    repo_info = await github_get(f"/repos/{owner}/{repo}")
    if "error" in repo_info:
        return repo_info

    default_branch = repo_info.get("default_branch", "main")

    # Fetch the full recursive tree (one API call, no pagination needed for most repos)
    tree_resp = await github_get(
        f"/repos/{owner}/{repo}/git/trees/{default_branch}",
        params={"recursive": "1"},
    )
    if "error" in tree_resp:
        return tree_resp

    items = tree_resp.get("tree", [])
    truncated = tree_resp.get("truncated", False)

    filtered = _build_tree(items, path, max_depth)

    return {
        "owner": owner,
        "repo": repo,
        "path": path or "/",
        "max_depth": max_depth,
        "truncated": truncated,
        "tree": filtered,
    }
