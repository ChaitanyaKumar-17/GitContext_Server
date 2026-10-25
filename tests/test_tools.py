"""
test_tools.py
~~~~~~~~~~~~~
Pytest suite for all five GitContext MCP tools.

Strategy:
  - Call each tool's underlying Python function directly (bypasses MCP layer).
  - Mock the GitHub API client functions (github_get / github_get_raw) so no
    real network calls are made and tests remain fast and deterministic.
  - Each tool has at minimum one SUCCESS case and one FAILURE case.
  - One test explicitly verifies that a rate-limit response is returned as a
    structured dict — never as a raised exception or raw traceback.

Run:
    pytest tests/ -v
"""

import pytest
from unittest.mock import AsyncMock, patch

# ── Import tool functions directly (bypass MCP protocol layer) ─────────────────
from server.tools.repo_structure import get_repo_structure
from server.tools.search_code import search_code
from server.tools.read_file import read_file, MAX_FILE_SIZE_BYTES
from server.tools.readme_summary import summarize_readme
from server.tools.recent_commits import get_recent_commits
from server.auth import verify_bearer_token

# ── pytest-asyncio configuration ──────────────────────────────────────────────
# Apply asyncio mark only to async test classes — sync classes opt out via pytestmark=[]
pytestmark = pytest.mark.asyncio


# ══════════════════════════════════════════════════════════════════════════════
# Helper fixtures / shared mock data
# ══════════════════════════════════════════════════════════════════════════════

FAKE_REPO_INFO = {"default_branch": "main", "full_name": "owner/repo"}

FAKE_TREE = {
    "tree": [
        {"path": "README.md",         "type": "blob", "size": 512},
        {"path": "src",               "type": "tree", "size": None},
        {"path": "src/main.py",       "type": "blob", "size": 1024},
        {"path": "src/utils.py",      "type": "blob", "size": 800},
        {"path": "tests",             "type": "tree", "size": None},
        {"path": "tests/test_main.py","type": "blob", "size": 640},
    ],
    "truncated": False,
}

FAKE_SEARCH_RESULTS = {
    "total_count": 3,
    "items": [
        {
            "path": "src/main.py",
            "html_url": "https://github.com/owner/repo/blob/main/src/main.py",
            "text_matches": [
                {
                    "fragment": "def connect(host, port):",
                    "matches": [{"text": "connect", "indices": [4, 11]}],
                }
            ],
        },
        {
            "path": "src/utils.py",
            "html_url": "https://github.com/owner/repo/blob/main/src/utils.py",
            "text_matches": [],
        },
    ],
}

FAKE_FILE_META = {"size": 512, "type": "file", "name": "README.md"}
FAKE_FILE_CONTENT = b"# Hello World\n\nThis is the README."

FAKE_COMMITS = [
    {
        "sha": "abc1234567890",
        "commit": {
            "message": "Fix bug in parser",
            "author": {"name": "Alice", "email": "alice@example.com", "date": "2024-01-15T10:00:00Z"},
        },
        "author": {"login": "alice"},
        "html_url": "https://github.com/owner/repo/commit/abc1234567890",
    },
    {
        "sha": "def9876543210",
        "commit": {
            "message": "Add feature X",
            "author": {"name": "Bob", "email": "bob@example.com", "date": "2024-01-14T09:00:00Z"},
        },
        "author": {"login": "bob"},
        "html_url": "https://github.com/owner/repo/commit/def9876543210",
    },
]

RATE_LIMITED = {"error": "rate_limited", "retry_after": 42}
NOT_FOUND    = {"error": "not_found", "message": "Resource not found: /repos/owner/repo"}


# ══════════════════════════════════════════════════════════════════════════════
# 1. get_repo_structure
# ══════════════════════════════════════════════════════════════════════════════

class TestGetRepoStructure:

    async def test_success_returns_tree(self):
        """Happy path: returns depth-limited file/folder tree."""
        with patch("server.tools.repo_structure.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [FAKE_REPO_INFO, FAKE_TREE]
            result = await get_repo_structure("owner", "repo", path="", max_depth=2)

        assert "error" not in result
        assert result["owner"] == "owner"
        assert result["repo"] == "repo"
        assert isinstance(result["tree"], list)
        assert len(result["tree"]) > 0
        assert result["truncated"] is False

    async def test_success_depth_filtering(self):
        """max_depth=1 should exclude entries more than 1 level deep."""
        with patch("server.tools.repo_structure.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [FAKE_REPO_INFO, FAKE_TREE]
            result = await get_repo_structure("owner", "repo", path="", max_depth=1)

        assert "error" not in result
        # src/main.py is depth 2 — should be excluded
        paths = [item["path"] for item in result["tree"]]
        assert "src/main.py" not in paths
        assert "README.md" in paths

    async def test_repo_not_found(self):
        """404 on repo info should propagate as structured not_found error."""
        with patch("server.tools.repo_structure.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = NOT_FOUND
            result = await get_repo_structure("owner", "nonexistent")

        assert result["error"] == "not_found"

    async def test_rate_limited_on_repo_info(self):
        """Rate-limit on repo info call should return structured rate_limited dict."""
        with patch("server.tools.repo_structure.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = RATE_LIMITED
            result = await get_repo_structure("owner", "repo")

        assert result["error"] == "rate_limited"
        assert "retry_after" in result


# ══════════════════════════════════════════════════════════════════════════════
# 2. search_code
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchCode:

    async def test_success_returns_matches(self):
        """Happy path: returns match list with path and text_matches."""
        with patch("server.tools.search_code.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = FAKE_SEARCH_RESULTS
            result = await search_code("owner", "repo", "connect")

        assert "error" not in result
        assert result["total_count"] == 3
        assert result["returned"] == 2
        assert result["matches"][0]["path"] == "src/main.py"
        assert len(result["matches"][0]["text_matches"]) == 1

    async def test_success_with_file_extension_filter(self):
        """Extension filter is appended to query correctly."""
        with patch("server.tools.search_code.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"total_count": 0, "items": []}
            result = await search_code("owner", "repo", "connect", file_extension="py")

        assert "error" not in result
        # Verify the query param included the extension qualifier
        call_params = mock_get.call_args[1]["params"]
        assert "extension:py" in call_params["q"]

    async def test_rate_limited_returns_structured_error_not_crash(self):
        """
        CRITICAL: rate-limit must return structured dict, NEVER raise exception.
        This is the explicit rate-limit path test required by the spec.
        """
        with patch("server.tools.search_code.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = RATE_LIMITED
            # Must not raise — result must be a dict with error key
            result = await search_code("owner", "repo", "anything")

        assert isinstance(result, dict), "Result must be a dict, not an exception"
        assert result.get("error") == "rate_limited", "Must surface rate_limited error"
        assert isinstance(result.get("retry_after"), int), "retry_after must be an int"

    async def test_returns_empty_on_no_results(self):
        """Zero results is valid — not an error."""
        with patch("server.tools.search_code.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"total_count": 0, "items": []}
            result = await search_code("owner", "repo", "zzznomatch")

        assert "error" not in result
        assert result["total_count"] == 0
        assert result["matches"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 3. read_file
# ══════════════════════════════════════════════════════════════════════════════

class TestReadFile:

    async def test_success_returns_content(self):
        """Happy path: returns file content as text."""
        with patch("server.tools.read_file.github_get",     new_callable=AsyncMock) as mock_get, \
             patch("server.tools.read_file.github_get_raw", new_callable=AsyncMock) as mock_raw:
            mock_get.return_value = FAKE_FILE_META
            mock_raw.return_value = FAKE_FILE_CONTENT
            result = await read_file("owner", "repo", "README.md")

        assert "error" not in result
        assert result["path"] == "README.md"
        assert result["size"] == 512
        assert "Hello World" in result["content"]

    async def test_file_too_large_returns_structured_error(self):
        """Files exceeding 30 KB limit must return file_too_large, not raw content."""
        oversized_meta = {"size": MAX_FILE_SIZE_BYTES + 1, "type": "file", "name": "big.py"}
        with patch("server.tools.read_file.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = oversized_meta
            result = await read_file("owner", "repo", "big.py")

        assert result["error"] == "file_too_large"
        assert result["size"] > MAX_FILE_SIZE_BYTES
        assert "suggestion" in result
        assert "search_code" in result["suggestion"]

    async def test_file_not_found(self):
        """404 on contents API should return not_found error."""
        with patch("server.tools.read_file.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = NOT_FOUND
            result = await read_file("owner", "repo", "missing.py")

        assert result["error"] == "not_found"

    async def test_directory_path_returns_is_directory_error(self):
        """Passing a directory path should return is_directory error."""
        with patch("server.tools.read_file.github_get", new_callable=AsyncMock) as mock_get:
            # GitHub returns a list for directories
            mock_get.return_value = [
                {"name": "file1.py", "type": "file"},
                {"name": "file2.py", "type": "file"},
            ]
            result = await read_file("owner", "repo", "src/")

        assert result["error"] == "is_directory"

    async def test_rate_limited_on_metadata(self):
        """Rate-limit on metadata call returns structured error."""
        with patch("server.tools.read_file.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = RATE_LIMITED
            result = await read_file("owner", "repo", "file.py")

        assert result["error"] == "rate_limited"


# ══════════════════════════════════════════════════════════════════════════════
# 4. summarize_readme
# ══════════════════════════════════════════════════════════════════════════════

class TestSummarizeReadme:

    async def test_success_returns_readme_content(self):
        """Happy path: returns raw README text."""
        with patch("server.tools.readme_summary.github_get_raw", new_callable=AsyncMock) as mock_raw:
            mock_raw.return_value = b"# MyProject\n\nA great library."
            result = await summarize_readme("owner", "repo")

        assert "error" not in result
        assert result["path"] == "README.md"
        assert "MyProject" in result["content"]
        assert result["size"] > 0

    async def test_falls_back_through_readme_candidates(self):
        """If README.md is missing, tries README.rst etc. before giving up."""
        call_count = 0

        async def side_effect(path, **kwargs):
            nonlocal call_count
            call_count += 1
            # First candidate (README.md) → not found
            if "README.md" in path:
                return {"error": "not_found", "message": "not found"}
            # Second candidate (README.rst) → success
            return b"My RST readme content"

        with patch("server.tools.readme_summary.github_get_raw", side_effect=side_effect):
            result = await summarize_readme("owner", "repo")

        assert "error" not in result
        assert result["path"] == "README.rst"
        assert call_count == 2

    async def test_no_readme_found_returns_not_found(self):
        """If ALL candidate files return 404, returns a not_found error."""
        with patch("server.tools.readme_summary.github_get_raw", new_callable=AsyncMock) as mock_raw:
            mock_raw.return_value = {"error": "not_found", "message": "not found"}
            result = await summarize_readme("owner", "repo")

        assert result["error"] == "not_found"

    async def test_rate_limited_propagates(self):
        """Rate-limit on README fetch returns structured rate_limited error."""
        with patch("server.tools.readme_summary.github_get_raw", new_callable=AsyncMock) as mock_raw:
            mock_raw.return_value = RATE_LIMITED
            result = await summarize_readme("owner", "repo")

        assert result["error"] == "rate_limited"


# ══════════════════════════════════════════════════════════════════════════════
# 5. get_recent_commits
# ══════════════════════════════════════════════════════════════════════════════

class TestGetRecentCommits:

    async def test_success_returns_commit_list(self):
        """Happy path: returns list of commits with expected fields."""
        with patch("server.tools.recent_commits.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = FAKE_COMMITS
            result = await get_recent_commits("owner", "repo", limit=2)

        assert "error" not in result
        assert result["count"] == 2
        commits = result["commits"]
        assert commits[0]["sha"] == "abc123456789"   # short 12-char SHA
        assert commits[0]["author"] == "Alice"
        assert commits[0]["message"] == "Fix bug in parser"
        assert commits[1]["sha"] == "def987654321"

    async def test_limit_capped_at_max(self):
        """limit > 50 should be silently capped at 50."""
        with patch("server.tools.recent_commits.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            await get_recent_commits("owner", "repo", limit=999)

        call_params = mock_get.call_args[1]["params"]
        assert call_params["per_page"] == 50

    async def test_path_filter_passed_to_api(self):
        """When path is provided, it's forwarded to the GitHub commits API."""
        with patch("server.tools.recent_commits.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            result = await get_recent_commits("owner", "repo", limit=5, path="src/main.py")

        call_params = mock_get.call_args[1]["params"]
        assert call_params.get("path") == "src/main.py"
        assert result["path"] == "src/main.py"

    async def test_repo_not_found(self):
        """404 on commits endpoint returns not_found error."""
        with patch("server.tools.recent_commits.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = NOT_FOUND
            result = await get_recent_commits("owner", "nonexistent")

        assert result["error"] == "not_found"

    async def test_rate_limited(self):
        """Rate-limit returns structured error dict."""
        with patch("server.tools.recent_commits.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = RATE_LIMITED
            result = await get_recent_commits("owner", "repo")

        assert result["error"] == "rate_limited"
        assert result["retry_after"] == 42


# ══════════════════════════════════════════════════════════════════════════════
# 6. auth.py — Bearer token verification (sync tests, no asyncio mark needed)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.no_cover   # sync — override module-level asyncio mark
class TestBearerTokenAuth:
    pytestmark: list = []  # clears module-level asyncio mark; these tests are sync

    def test_correct_token_accepted(self, monkeypatch):
        monkeypatch.setenv("MCP_BEARER_TOKEN", "mysecret")
        assert verify_bearer_token("Bearer mysecret") is True

    def test_wrong_token_rejected(self, monkeypatch):
        monkeypatch.setenv("MCP_BEARER_TOKEN", "mysecret")
        assert verify_bearer_token("Bearer wrongtoken") is False

    def test_missing_header_rejected(self, monkeypatch):
        monkeypatch.setenv("MCP_BEARER_TOKEN", "mysecret")
        assert verify_bearer_token(None) is False

    def test_non_bearer_scheme_rejected(self, monkeypatch):
        monkeypatch.setenv("MCP_BEARER_TOKEN", "mysecret")
        assert verify_bearer_token("Basic mysecret") is False

    def test_empty_env_var_rejects_all(self, monkeypatch):
        monkeypatch.setenv("MCP_BEARER_TOKEN", "")
        assert verify_bearer_token("Bearer anything") is False


# ══════════════════════════════════════════════════════════════════════════════
# 7. github_client.py — rate-limit parsing (unit test)
# ══════════════════════════════════════════════════════════════════════════════

class TestGithubClientRateLimit:
    """
    Explicitly tests that the github_client converts 429/403 responses into
    a structured dict — never raises an exception.
    This is the spec-required rate-limit path verification.
    """

    async def test_429_returns_structured_dict_not_exception(self):
        """
        A 429 response from GitHub must produce:
          {"error": "rate_limited", "retry_after": <int or None>}
        and must NOT raise any exception.
        """
        import httpx
        import respx

        with respx.mock:
            respx.get("https://api.github.com/repos/owner/repo").mock(
                return_value=httpx.Response(
                    429,
                    headers={"Retry-After": "30"},
                    json={"message": "rate limit exceeded"},
                )
            )
            from server.github_client import github_get
            result = await github_get("/repos/owner/repo")

        # Must be a dict — not a raised exception
        assert isinstance(result, dict)
        assert result["error"] == "rate_limited"
        assert result["retry_after"] == 30

    async def test_403_also_treated_as_rate_limit(self):
        """GitHub sends 403 for secondary rate limits — must also be structured."""
        import httpx
        import respx

        with respx.mock:
            respx.get("https://api.github.com/search/code").mock(
                return_value=httpx.Response(
                    403,
                    json={"message": "secondary rate limit"},
                )
            )
            from server.github_client import github_get
            result = await github_get("/search/code")

        assert isinstance(result, dict)
        assert result["error"] == "rate_limited"

    async def test_timeout_returns_structured_dict(self):
        """Timeouts must return structured error, never propagate TimeoutException."""
        import httpx
        import respx

        with respx.mock:
            respx.get("https://api.github.com/repos/owner/repo").mock(
                side_effect=httpx.TimeoutException("timed out")
            )
            from server.github_client import github_get
            result = await github_get("/repos/owner/repo")

        assert isinstance(result, dict)
        assert result["error"] == "timeout"
