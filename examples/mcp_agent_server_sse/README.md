# MCP Server example

To use in claude desktop, insert the following in `claude_desktop_config.json` and restart the Claude Desktop client.

```json
{
  "mcpServers": {
    "mcp-agent": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/PARENT/FOLDER",
        "run",
        "server.py"
      ]
    }
  }
}
```

> [!WARNING]
> You may need to put the full path to the uv executable in the command field. You can get this by running `which uv` on MacOS/Linux or `where uv` on Windows.

<img width="780" alt="Image" src="https://github.com/user-attachments/assets/e4a1b283-c739-43a2-80b8-827adeac9962" />

To use the MCP server with a client:

```bash
uv run client.py server.py
```
