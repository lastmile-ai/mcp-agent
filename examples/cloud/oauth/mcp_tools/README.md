# OAuth MCP Tools Example

This example demonstrates how to integrate OAuth 2.0-enabled MCP servers within mcp-agent. The example exposes a `github_org_search` tool that calls the GitHub MCP server, requiring OAuth authorization.

## What's included

- `main.py` – exposes a `github_org_search` tool that integrates with the GitHub MCP server using OAuth 2.0
- `mcp_agent.config.yaml` – configures OAuth settings including callback URLs, flow timeout, and token store settings
- `mcp_agent.secrets.yaml.example` – template for storing GitHub OAuth credentials (client ID, secret, and access token)

## Features

- **Interactive (lazy) authorization**: When the tool is invoked without a cached token, the server issues an `auth/request` message and the client opens the browser to interactively complete the GitHub sign-in
- **Pre-authorized workflows**: Leverage the workflows-store-credentials mcp-agent tool to cache a token for a specified workflow before the workflow is run. Once the token is saved, the workflow can access the downstream MCP server without further user interaction
- **GitHub repository search**: Search GitHub repositories within organizations using the OAuth-protected GitHub MCP server
- **Token caching**: OAuth tokens are cached and reused across runs using a stable session ID

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- GitHub OAuth App for authentication

## Configuration

Before running the example, you'll need to create a GitHub OAuth App and configure the credentials.

### GitHub OAuth App Setup

1. Create a GitHub OAuth App (Settings → Developer settings → OAuth Apps)

2. Set the **Authorization callback URL** to `http://127.0.0.1:33418/callback`

   > The example pins its loopback listener to that port, so the value must match exactly.

3. For testing in MCP Inspector, add an additional callback URL: `http://localhost:6274/oauth/callback`

   > [!NOTE]
   > GitHub does not accept the RFC 8707 `resource` parameter, so the example disables it via `include_resource_parameter: false` in the config.

4. Obtain a GitHub personal access token from https://github.com/settings/personal-access-tokens

### Secrets Configuration

1. Copy the example secrets file:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

2. Edit `mcp_agent.secrets.yaml` to add your GitHub OAuth credentials:

```yaml
mcp:
  servers:
    github:
      auth:
        oauth:
          client_id: "your-github-client-id"
          client_secret: "your-github-client-secret"
          access_token: "your-github-access-token"
```

## Test Locally

1. Install dependencies:

```bash
cd examples/cloud/oauth/mcp_tools
uv pip install -r requirements.txt
```

2. Start the mcp-agent server locally with SSE transport:

```bash
uv run main.py
```

The server uses a stable session ID so the OAuth token is cached and reused across runs. Once the first authorization completes, subsequent invocations should return immediately without reopening the browser.

3. Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to test the OAuth-enabled MCP tools:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
```

4. In MCP Inspector:
   - The server will initiate the OAuth 2.0 authorization flow when you first call the `github_org_search` tool
   - Complete the GitHub authorization in your browser
   - Once authenticated, test the `github_org_search` tool with an organization name (e.g., "github")
   - The tool will search for repositories in the specified organization and return the top 5 results
   - To pre-authorize the `github_org_search` workflow, call the `workflows-store-credentials` tool with:

```json
{
  "workflow_name": "github_org_search_activity",
  "tokens": [
    {
        "access_token": access_token,
        "server_name": "github",
    }
  ]
}
```

## Deploy to mcp-agent Cloud

You can deploy this OAuth-enabled MCP-Agent app as a hosted mcp-agent app in the Cloud.

1. In your terminal, authenticate into mcp-agent cloud by running:

```bash
uv run mcp-agent login
```

2. You will be redirected to the login page, create an mcp-agent cloud account through Google or Github

3. Set up your mcp-agent cloud API Key and copy & paste it into your terminal

```bash
uv run mcp-agent login
INFO: Directing to MCP Agent Cloud API login...
Please enter your API key 🔑:
```

4. In your terminal, deploy the MCP app:

```bash
uv run mcp-agent deploy oauth-mcp-tools
```

5. When prompted, specify the type of secret to save your GitHub OAuth credentials. Select (1) deployment secret so that they are available to the deployed server.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client that supports the MCP protocol.

### MCP Inspector

You can inspect and test the deployed server using [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

This will launch the MCP Inspector UI where you can:

- Complete the OAuth 2.0 authorization flow for GitHub
- See all available tools (including `github_org_search`)
- Test the `github_org_search` tool with different organization queries

Make sure Inspector is configured with the following settings:

| Setting          | Value                                               |
| ---------------- | --------------------------------------------------- |
| _Transport Type_ | _SSE_                                               |
| _SSE_            | _https://[server_id].deployments.mcp-agent.com/sse_ |
| _Header Name_    | _Authorization_                                     |
| _Bearer Token_   | _your-mcp-agent-cloud-api-token_                    |

## Further Reading

More details on OAuth authorization and the MCP protocol can be found at [https://modelcontextprotocol.io/specification/draft/basic/authorization](https://modelcontextprotocol.io/specification/draft/basic/authorization).
