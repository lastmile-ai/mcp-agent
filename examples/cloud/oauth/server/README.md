# OAuth protected resource example

This example shows how to integrate OAuth2 authentication to protect your MCP.

## 1. App set up

First, clone the repo and navigate to the functions example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/oauth/protected_by_oauth
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

## 2. Client registration
To protect your MCP with OAuth2, you first need to register your application with an OAuth2 provider, as MCP follows the Dynamic Client Registration Protocol.
You can configure either your own OAuth2 server, or use the one provided by MCP Agent Cloud (https://auth.mcp-agent.com).

If you do not have a client registered already, you can use the `registration.py` script provided with this example.
At the top of the file,
1. update the URL for your authentication server,
2. set the redirect URIs to point to your MCP endpoint (e.g. `https://your-mcp-endpoint.com/callback`), and
3. set the name for your client.

Run the script to register your client:
```bash
uv run registration.py
```

You should see something like

```
Client registered successfully!
{
  # detailed json response
}

=== Save these credentials ===
Client ID: abc-123
Client Secret: xyz-987
```

Take a note of the client id and client secret printed at the end, as you will need them in the next step.

## 3. Configure your MCP
Next, you need to configure your MCP to use the OAuth2 credentials you just created.
In `main.py`, update these settings:

```python
auth_server = "<auth server url>"
resource_server = "http://localhost:8000"  # This server's URL

client_id = "<the client id returned by the registration.py script>"
client_secret = "<the client secret returned by the registration.py script>"
```

## 4. Run the example

With these in place, you can run the server using

```python
uv run main.py
```

This will start an MCP server protected by OAuth2.
You can test it using an MCP client that supports OAuth2 authentication, such as [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector).


## Further reading
More details on oauth authorization and the MCP protocol can be found at [https://modelcontextprotocol.io/specification/draft/basic/authorization](https://modelcontextprotocol.io/specification/draft/basic/authorization).
