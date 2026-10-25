"""
Claude Desktop config snippet for M1 (local stdio transport).

Add this to your Claude Desktop config file at:
  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
  Windows: %APPDATA%\Claude\claude_desktop_config.json

{
  "mcpServers": {
    "gitcontext": {
      "command": "D:\\Chaitanya\\AIML\\Project\\GitContext_Server\\.venv\\Scripts\\python.exe",
      "args": ["-m", "server.main"],
      "cwd": "D:\\Chaitanya\\AIML\\Project\\GitContext_Server",
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here",
        "MCP_BEARER_TOKEN": "your-secret-token"
      }
    }
  }
}
"""
