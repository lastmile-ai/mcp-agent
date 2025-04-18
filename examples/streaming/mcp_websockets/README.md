# MCP Websocket example

This example shows a basic agent that can connect to an MCP server over websockets

Setup instructions:

1. Get your GitHub PAT from https://github.com/settings/personal-access-tokens, make sure you have read access for repositories.
2. Base64-encode the following:

```json
{
  "githubPersonalAccessToken": "YOUR_GITHUB_PAT"
}
```

3. Copy the `mcp_agent.secrets.yaml` file, and update it with your OpenAI API key, and the websocket url with the Base64-encoded string:

```yaml
openai:
  api_key: openai_api_key

mcp:
  servers:
    smithery-github:
      url: "wss://server.smithery.ai/@smithery-ai/github/ws?config=BASE64_ENCODED_CONFIG"
```

Finally, run `uv run main.py <your github username>`. E.g. `uv run main.py saqadri`

<img width="979" alt="image" src="https://github.com/user-attachments/assets/55ca84fe-b9f3-4930-9f8f-3e7fb7449e5b" />
