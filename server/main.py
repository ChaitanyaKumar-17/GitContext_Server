"""
main.py
~~~~~~~
GitContext MCP Server — M3: Streamable HTTP transport + Bearer-token auth

Switched from stdio (M1) to Streamable HTTP so the server can be deployed and
reached over a real network connection (M4/M5).

Auth middleware:
  Every request must carry:  Authorization: Bearer <MCP_BEARER_TOKEN>
  Missing / invalid token  → 401 Unauthorized (structured JSON body)

Run locally (HTTP mode):
    python -m server.main

The server listens on PORT (env var, default 8000).

Add to Claude Desktop as a REMOTE server (after deployment):
  {
    "gitcontext-remote": {
      "type": "http",
      "url": "https://<your-deployed-url>/mcp",
      "headers": { "Authorization": "Bearer <MCP_BEARER_TOKEN>" }
    }
  }
"""

import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from server.auth import verify_bearer_token
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

PORT = int(os.getenv("PORT", "8000"))


# ── Auth middleware ────────────────────────────────────────────────────────────

class BearerAuthMiddleware(BaseHTTPMiddleware):
    """
    Rejects any request without a valid Bearer token with a clean 401.
    Health-check path (/health) is exempt so deployment platforms can probe it.
    """

    EXEMPT_PATHS = {"/health"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not verify_bearer_token(auth_header):
            log.warning(
                "auth_rejected method=%s path=%s ip=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Valid Bearer token required in Authorization header.",
                },
            )

        return await call_next(request)


# ── FastMCP app ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="GitContext Server",
    instructions=(
        "A set of tools for exploring GitHub repositories: structure inspection, "
        "code search, file reading, README summarization, and commit history. "
        "All tools accept `owner` and `repo` as the first two arguments, "
        "targeting any public (or accessible private) GitHub repository."
    ),
)


# ── Logging helper ─────────────────────────────────────────────────────────────

def _log_tool(name: str, kwargs: dict, result: Any, latency_ms: int) -> None:
    status = "error" if isinstance(result, dict) and "error" in result else "ok"
    log.info(
        "tool=%s args=%s status=%s latency_ms=%d",
        name,
        kwargs,
        status,
        latency_ms,
    )
    if status == "error":
        log.warning("tool=%s error=%s", name, result.get("error"))


# ── Tool registrations ─────────────────────────────────────────────────────────

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


# ── Build the ASGI app with auth middleware ────────────────────────────────────

def build_app():
    """
    Returns the Starlette ASGI app with BearerAuthMiddleware wrapping the
    FastMCP HTTP transport. Import this in Dockerfile / uvicorn.

    FastMCP 4.x requires its lifespan to be forwarded to the parent Starlette
    app so the StreamableHTTP session manager task group is initialised.
    """
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse as _JSONResponse

    async def health(request):
        return _JSONResponse({"status": "ok", "server": "GitContext MCP Server"})

    mcp_app = mcp.http_app(path="/mcp")

    # Parent app — must forward mcp_app.router.lifespan_context so FastMCP's
    # session manager task group is started before requests arrive.
    app = Starlette(
        lifespan=mcp_app.router.lifespan_context,
        routes=[
            Route("/health", health),
            Mount("/", app=mcp_app),
        ],
    )
    # Add auth middleware to the parent app (wraps all routes including /mcp)
    app.add_middleware(BearerAuthMiddleware)
    return app


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    log.info("Starting GitContext MCP Server (HTTP transport) on port %d", PORT)
    log.info("MCP endpoint: http://0.0.0.0:%d/mcp", PORT)
    log.info("Health check: http://0.0.0.0:%d/health", PORT)

    app = build_app()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
