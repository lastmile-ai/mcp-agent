# OAuth Protected Server Example

This example demonstrates how to secure an mcp-agent server with OAuth 2.0 authentication.

## What's included

- `main.py` – exposes a `hello_world` tool that demonstrates authenticated user access with personalized responses based on OAuth claims
- `registration.py` – helper script to dynamically register your OAuth client with an authorization server using the Dynamic Client Registration Protocol
- `mcp_agent.config.yaml` – configures authorization settings including issuer URL, required scopes, and OAuth callback settings
- `mcp_agent.secrets.yaml.example` – template for storing OAuth client credentials (client ID and secret)

## Features

- **OAuth 2.0 authentication**: Protects MCP server endpoints with industry-standard OAuth 2.0 authorization
- **Dynamic client registration**: Automatically registers OAuth clients following the Dynamic Client Registration Protocol
- **User context access**: Tools can access authenticated user information including claims and subject IDs
- **Flexible provider support**: Works with mcp-agent cloud auth server or your own OAuth 2.0 provider

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- OAuth 2.0 provider (e.g., mcp-agent cloud auth server at https://auth.mcp-agent.com or your own)

## Configuration

Before running the example, you'll need to register an OAuth client and configure the server.

### Client Registration

If you do not have a client registered already, you can use the `registration.py` script provided with this example.

1. First, ensure `mcp_agent.config.yaml` has the correct values for:

- `authorization.issuer_url`: authorization server issuing the client ID and secret; by default this will be the mcp-agent cloud auth server (https://auth.mco-agent.com)
- `oauth.callback_base_url`: base URL for oauth callbacks; by default this will be the local server URL (http://localhost:8000)

2. Install dependencies:

```bash
cd examples/cloud/oauth/server
uv pip install -r requirements.txt
```

3. Run the registration script:

```bash
uv run registration.py
```

The script will register your client with the authorization server (configured in `mcp_agent.config.yaml`) and output credentials:

```
Client registered successfully!
{
  # detailed json response
}

=== Save these credentials ===
Client ID: abc-123
Client Secret: xyz-987
```

4. Save the `Client ID` and `Client Secret` for the next step.

> The registration script automatically configures redirect URIs for the server (as specified by `oauth.callback_base_url` in the `mcp_agent.config.yaml`) and MCP Inspector (`http://localhost:6274/oauth/callback`). For production deployments, update the `oauth.callback_base_url` in `mcp_agent.config.yaml` to match your deployment URL, e.g. `https://<server_id>.deployments.mcp-agent.com`.

### Secrets Configuration

1. Copy the example secrets file:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

2. Edit `mcp_agent.secrets.yaml` to add your OAuth credentials:

```yaml
authorization:
  client_id: <client id from registration.py>
  client_secret: <client secret from registration.py>
  expected_audiences:
    - <client id from registration.py>
```

> The `expected_audiences` field should match your client ID to ensure tokens are issued for your application.

## Test Locally

1. Install dependencies:

```bash
uv pip install -r requirements.txt
```

2. Start the mcp-agent server locally with SSE transport:

```bash
uv run main.py
```

3. Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to test the OAuth-protected server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
```

4. In MCP Inspector:

   - Specify Client ID and Client Secret in the OAuth 2.0 Flow Authentication section
   - The server will initiate the OAuth 2.0 authorization flow
   - Complete the authorization in your browser
   - Once authenticated, test the `hello_world` tool
   - The tool will respond with a personalized greeting using your authenticated user information

5. Observe how the tool accesses user context:
   - If a username claim is present: "Hello, [username]!"
   - Otherwise: "Hello, user with ID [subject]!"

## Deploy to mcp-agent Cloud

You can deploy this OAuth-protected MCP-Agent app as a hosted mcp-agent app in the Cloud.

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
uv run mcp-agent deploy oauth-example
```

5. When prompted, specify the type of secret to save your OAuth client credentials. Select (1) deployment secret so that they are available to the deployed server.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

6. After initial deployment, update the authorization and oauth configuration in `mcp_agent.config.yaml` to use your deployed server URL:

- Set `authorization.resource_server_url` to `https://<server_id>.deployments.mcp-agent.com`
- Set `oauth.callback_base_url` to `https://<server_id>.deployments.mcp-agent.com`

7. Then re-run the registration script to get new credentials and set them in `mcp_agent.secrets.yaml`

8. Finally, redeploy the server with the updated configuration

```bash
uv run mcp-agent deploy oauth-example
```

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client that supports OAuth 2.0 authentication, just like any other OAuth-protected MCP server.

### MCP Inspector

You can inspect and test the deployed server using [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

This will launch the MCP Inspector UI where you can:

- Complete the OAuth 2.0 authorization flow
- See all available tools
- Test the `hello_world` tool with your authenticated user context

Make sure Inspector is configured with the following settings:

| Setting          | Value                                               |
| ---------------- | --------------------------------------------------- |
| _Transport Type_ | _SSE_                                               |
| _SSE_            | _https://[server_id].deployments.mcp-agent.com/sse_ |

> [!NOTE]
> When connecting with MCP Inspector, you will be redirected to complete the OAuth authorization flow in your browser before being able to use the server.

## Further Reading

More details on OAuth authorization and the MCP protocol can be found at [https://modelcontextprotocol.io/specification/draft/basic/authorization](https://modelcontextprotocol.io/specification/draft/basic/authorization).
