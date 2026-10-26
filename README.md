# GitContext MCP Server

A **live, authenticated, remote MCP server** that exposes 5 GitHub repository analysis tools to Claude Desktop (and any MCP-compatible client).

Built with [FastMCP](https://github.com/jlowin/fastmcp) · Deployed on [Render](https://render.com) · Protected by Bearer-token auth

---

## Architecture

```
Claude Desktop
     │  stdio
     ▼
 mcp-remote (npx)          ← local bridge process
     │  HTTPS + Bearer token
     ▼
Render (Docker container)
     │
 FastMCP / Starlette
     │
 GitHub REST API v3
```

**Why `mcp-remote`?**  
Claude Desktop's config file only supports `stdio` commands natively. `mcp-remote` acts as a local stdio↔HTTP bridge, forwarding MCP messages to the remote Render server with your Bearer token injected automatically.

---

## Tools (5)

| Tool | Description |
|------|-------------|
| `get_repo_structure` | Depth-limited file/folder tree via the GitHub Trees API |
| `search_code` | GitHub Code Search — returns paths, URLs, and matched snippets |
| `read_file` | Raw file content (≤ 30 KB guardrail; structured error for larger files) |
| `summarize_readme` | Raw README content returned for the model to summarize |
| `get_recent_commits` | Commit log with optional path filter; limit capped at 50 |

All tools accept `owner` and `repo` as their first two arguments and target any public (or accessible private) GitHub repository.

---

## Quickstart

### Prerequisites

- [Node.js v18+](https://nodejs.org/) (for `mcp-remote`)
- [Claude Desktop](https://claude.ai/download)
- A GitHub Personal Access Token (for GitHub API rate limits)

### Remote config (connect to the live Render server)

Edit your Claude Desktop config file:

- **Windows (Store):** `%LOCALAPPDATA%\Claude-Data\claude_pzs8sxrjxfjjc\claude_desktop_config.json`
- **Windows (direct install):** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the following inside the `"mcpServers"` object:

```json
{
  "mcpServers": {
    "gitcontext": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://gitcontext-server.onrender.com/mcp",
        "--header",
        "Authorization:Bearer ${MCP_TOKEN}"
      ],
      "env": {
        "MCP_TOKEN": "<your-mcp-bearer-token>"
      }
    }
  }
}
```

Fully quit Claude Desktop (system tray → Quit) and relaunch. On first connect, Render may take up to 60 seconds to wake from its free-tier sleep.

### Local dev config (stdio, no Docker needed)

```json
{
  "mcpServers": {
    "gitcontext": {
      "command": "/absolute/path/to/.venv/Scripts/python.exe",
      "args": ["-m", "server.main"],
      "cwd": "/absolute/path/to/GitContext_Server",
      "env": {
        "GITHUB_TOKEN": "<your-github-pat>",
        "MCP_BEARER_TOKEN": "<your-mcp-bearer-token>",
        "PYTHONPATH": "/absolute/path/to/GitContext_Server"
      }
    }
  }
}
```

> **Note:** On Windows use double backslashes or forward slashes for paths.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token. Authenticates GitHub API calls (higher rate limits). Generate at [github.com/settings/tokens](https://github.com/settings/tokens) — `public_repo` scope is sufficient for public repos. |
| `MCP_BEARER_TOKEN` | Yes | Secret token that Claude Desktop (via `mcp-remote`) must send in every request. Protects the deployed server from unauthorized access. |
| `PORT` | No | HTTP port for the server (default: `8000`). Render sets this automatically. |

Copy `.env.example` to `.env` and fill in values for local development:

```bash
cp .env.example .env
```

---

## Local Development

```bash
# 1. Clone
git clone https://github.com/ChaitanyaKumar-17/GitContext_Server.git
cd GitContext_Server

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # adds pytest, respx

# 4. Configure environment
cp .env.example .env
# Edit .env with your GITHUB_TOKEN and MCP_BEARER_TOKEN

# 5. Run locally (HTTP mode on port 8000)
python -m server.main

# 6. Run tests
pytest
```

### Health check

```bash
curl http://localhost:8000/health
# → {"status":"ok","server":"GitContext MCP Server"}
```

### Manual MCP call (with auth)

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer <MCP_BEARER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

## Tests

```bash
pytest -v
```

30 tests covering all 5 tools:
- Happy-path responses
- GitHub 404 / 403 / 429 → structured errors (no raw tracebacks)
- Rate-limit path explicitly tested
- 30 KB file size guardrail
- Bearer auth middleware (valid / missing / invalid token)

---

## Deployment (Render)

The server is containerized via Docker and deployed to Render's free tier.

### Deploy your own instance

1. **Fork** this repository on GitHub

2. **Create a new Web Service** on [render.com](https://render.com):
   - Connect your GitHub fork
   - Runtime: **Docker**
   - Branch: `main`

3. **Set environment variables** in Render dashboard → Environment:
   ```
   GITHUB_TOKEN      = <your-github-pat>
   MCP_BEARER_TOKEN  = <generate a strong random token>
   ```
   Generate a token:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

4. **Set health check path** to `/health` (Render dashboard → Settings → Health Check Path)

5. Render will build the Docker image and deploy automatically on every push to `main`.

> **Free tier note:** Render spins down services after 15 minutes of inactivity. The first request after idle takes ~50 seconds to wake. This is normal — subsequent requests are fast.

---

## Token Rotation

To rotate `MCP_BEARER_TOKEN`:

1. Generate a new token:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Update the environment variable in Render dashboard → Environment → `MCP_BEARER_TOKEN`
3. Trigger a redeploy (Render dashboard → Manual Deploy, or push a commit)
4. Update `MCP_TOKEN` in your Claude Desktop config file
5. Fully quit and relaunch Claude Desktop

---

## Project Structure

```
GitContext_Server/
├── server/
│   ├── main.py              # FastMCP app, BearerAuthMiddleware, /health route
│   ├── auth.py              # verify_bearer_token()
│   ├── github_client.py     # httpx client, structured error handling
│   └── tools/
│       ├── repo_structure.py
│       ├── search_code.py
│       ├── read_file.py
│       ├── readme_summary.py
│       └── recent_commits.py
├── tests/
│   └── test_tools.py        # 30 tests (pytest + pytest-asyncio + respx)
├── Dockerfile               # Multi-stage, python:3.12-slim, non-root user
├── .dockerignore
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── pytest.ini
└── README.md
```

---

## Design Decisions

- **No LLM calls inside tools** — `summarize_readme` returns raw README content for the calling model to interpret
- **Structured errors only** — all error paths return `{"error": "...", "message": "..."}` JSON; Python tracebacks never reach the client
- **Exactly 5 tools** — focused, composable, no scope creep
- **Bearer auth on every route** — `/health` is the only exempt endpoint (needed for Render probes)
- **30 KB file guardrail** — `read_file` rejects oversized files with a structured error pointing users to `search_code`

---

## License

MIT
