# MCP Websocket example

This example shows a basic agent that can connect to an MCP server over websockets

<img width="979" alt="image" src="https://github.com/user-attachments/assets/55ca84fe-b9f3-4930-9f8f-3e7fb7449e5b" />

---

## `1` App set up

First, clone the repo and navigate to the MCP Websocket example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_websockets
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `1.1` Generate a GitHub Personal Access Token (PAT)

Get your GitHub PAT from https://github.com/settings/personal-access-tokens, make sure you have read access for repositories.

> [!NOTE]
> You have to encode the _json_ object with your github personal access token as a Base64 string

Base64-encode the following:

```json
{
  "githubPersonalAccessToken": "YOUR_GITHUB_PAT"
}
```

On a Mac, you can run the following command to get the Base64 encoded string:

```bash
base64 <<< {"githubPersonalAccessToken": "YOUR_GITHUB_PAT"}
```

## `2` Set up secrets and environment variables

Copy and configure your secrets and env variables:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Then open `mcp_agent.secrets.yaml` and update it with your OpenAI API key, and the websocket url with the Base64-encoded string:

```yaml
openai:
  api_key: openai_api_key

mcp:
  servers:
    smithery-github:
      url: "wss://server.smithery.ai/@smithery-ai/github/ws?config=BASE64_ENCODED_CONFIG"
```

## `3` Run locally

Run your MCP Agent app:

```bash
uv run main.py <your github username>
```

Example:

```bash
uv run main.py saqadri
```
