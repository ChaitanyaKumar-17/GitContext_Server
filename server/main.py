"""
main.py
~~~~~~~
GitContext MCP Server — M1: stdio transport

Entry point for the FastMCP server. Registers all five tools and wires up
structured logging so every tool call is traced with name, args, latency, and
success/failure status.

Run locally:
    python -m server.main

Add to Claude Desktop (mcp_servers in config.json):
    {
      "gitcontext": {
        "command": "python",
        "args": ["-m", "server.main"],
        "cwd": "/path/to/GitContext_Server",
        "env": {
          "GITHUB_TOKEN": "ghp_...",
          "MCP_BEARER_TOKEN": "your-secret"
        }
      }
    }
"""

import logging
import time
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from server.tools.repo_structure import get_repo_structure as _get_repo_structure
from server.tools.search_code import search_code as _search_code
from server.tools.read_file import read_file as _read_file
from server.tools.readme_summary import summarize_readme as _summarize_readme
from server.tools.recent_commits import get_recent_commits as _get_recent_commits

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("gitcontext")

mcp = FastMCP(
    name="GitContext Server",
    instructions=(
        "A set of tools for exploring GitHub repositories: structure inspection, "
        "code search, file reading, README summarization, and commit history. "
        "All tools accept `owner` and `repo` as the first two arguments, "
        "targeting any public (or accessible private) GitHub repository."
    ),
)


# ── Logging decorator ─────────────────────────────────────────────────────────

def _log_tool(name: str, kwargs: dict, result: Any, latency_ms: int) -> None:
    status = "error" if isinstance(result, dict) and "error" in result else "ok"
    log.info(
        "tool=%s args=%s status=%s latency_ms=%d",
        name,
        {k: v for k, v in kwargs.items()},
        status,
        latency_ms,
    )
    if status == "error":
        log.warning("tool=%s error=%s", name, result.get("error"))


# ── Tool registrations ────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Return the file/folder tree for a given path in a GitHub repository. "
        "Results are depth-limited (max_depth, default 2) to avoid dumping large repos. "
        "Use path='' for the repo root."
    )
)
async def get_repo_structure(
    owner: str,
    repo: str,
    path: str = "",
    max_depth: int = 2,
) -> dict:
    t0 = time.monotonic()
    result = await _get_repo_structure(owner, repo, path, max_depth)
    _log_tool("get_repo_structure", {"owner": owner, "repo": repo, "path": path, "max_depth": max_depth}, result, int((time.monotonic() - t0) * 1000))
    return result


@mcp.tool(
    description=(
        "Search for code in a GitHub repository using the GitHub Code Search API. "
        "Returns file paths, URLs, and matched snippets. "
        "Optionally filter by file_extension (e.g. 'py', 'ts')."
    )
)
async def search_code(
    owner: str,
    repo: str,
    query: str,
    file_extension: str | None = None,
) -> dict:
    t0 = time.monotonic()
    result = await _search_code(owner, repo, query, file_extension)
    _log_tool("search_code", {"owner": owner, "repo": repo, "query": query, "file_extension": file_extension}, result, int((time.monotonic() - t0) * 1000))
    return result


@mcp.tool(
    description=(
        "Fetch the raw text content of a file from a GitHub repository. "
        "Files larger than 30 KB are rejected with a structured error — "
        "use search_code to locate specific sections in large files instead. "
        "ref defaults to 'main'; pass a branch, tag, or commit SHA to override."
    )
)
async def read_file(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main",
) -> dict:
    t0 = time.monotonic()
    result = await _read_file(owner, repo, path, ref)
    _log_tool("read_file", {"owner": owner, "repo": repo, "path": path, "ref": ref}, result, int((time.monotonic() - t0) * 1000))
    return result


@mcp.tool(
    description=(
        "Fetch the raw README content for a GitHub repository. "
        "The content is returned as-is for the calling model to summarize — "
        "no nested LLM call is made inside this tool."
    )
)
async def summarize_readme(owner: str, repo: str) -> dict:
    t0 = time.monotonic()
    result = await _summarize_readme(owner, repo)
    _log_tool("summarize_readme", {"owner": owner, "repo": repo}, result, int((time.monotonic() - t0) * 1000))
    return result


@mcp.tool(
    description=(
        "Return recent commit log entries (SHA, author, message, date) for a GitHub repository. "
        "Optionally filter to a specific file or directory path. "
        "limit defaults to 10; maximum is 50."
    )
)
async def get_recent_commits(
    owner: str,
    repo: str,
    limit: int = 10,
    path: str | None = None,
) -> dict:
    t0 = time.monotonic()
    result = await _get_recent_commits(owner, repo, limit, path)
    _log_tool("get_recent_commits", {"owner": owner, "repo": repo, "limit": limit, "path": path}, result, int((time.monotonic() - t0) * 1000))
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting GitContext MCP Server (stdio transport)")
    mcp.run(transport="stdio")
