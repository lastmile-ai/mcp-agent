# OAuth Interactive Tool Example

This example shows the end-to-end OAuth **authorization code** flow for a
simple synchronous MCP tool. The MCP server exposes a `github_org_search`
tool that calls the GitHub MCP server. When the tool is invoked without a
cached token, the server issues an `auth/request` message and the client opens
the browser so you can complete the GitHub sign-in.

## Prerequisites

1. Create a GitHub OAuth App (Settings → Developer settings → OAuth Apps)
   with callback URL `http://localhost:8000/internal/oauth/callback`.
2. Export the client credentials:

   ```bash
   export GITHUB_CLIENT_ID="your_client_id"
   export GITHUB_CLIENT_SECRET="your_client_secret"
   ```

3. Install dependencies (from the repository root):

   ```bash
   pip install -e .
   ```

## Running

Start the MCP server in one terminal:

```bash
python examples/oauth/interactive_tool/server.py
```

In another terminal, run the client:

```bash
python examples/oauth/interactive_tool/client.py
```

The client will display an authorization prompt. Approve it in the browser
and GitHub will redirect back to the local callback handler. Once completed,
the tool result is printed in the client terminal.

Subsequent tool invocations reuse the stored token until it expires or is
revoked.
