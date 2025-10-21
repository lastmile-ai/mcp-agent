# Workflow Pre-Authorize Example

This example shows how to seed OAuth credentials for asynchronous workflows.
The client calls the `workflows-store-credentials` tool to cache a token for a
specific workflow before the workflow runs. Once the token is saved, the
workflow can access the downstream MCP server without further user interaction.

## Prerequisites

1. Copy the secrets template and provide your GitHub OAuth client credentials:

   ```bash
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   ```

   Edit the copied file (or export matching environment variables) so the GitHub
   entry contains your OAuth app's client id and client secret.

2. Obtain a GitHub access token (e.g., via the interactive example) and
   export it before running the client:

   ```bash
   export GITHUB_ACCESS_TOKEN="github_pat_xxx"
   ```

3. Install dependencies:

   ```bash
   pip install -e .
   # optional redis support
   # pip install -e .[redis]
   ```

4. (Optional) To persist tokens in Redis instead of memory, start a Redis
   instance and set `OAUTH_REDIS_URL`, for example:

   ```bash
   docker run --rm -p 6379:6379 redis:7-alpine
   export OAUTH_REDIS_URL="redis://127.0.0.1:6379"
   ```

## Running

1. Start the workflow server:

   ```bash
   python examples/oauth/pre_authorize/main.py
   ```

2. In another terminal, run the client to seed the token and execute the
   workflow:

   ```bash
   python examples/oauth/pre_authorize/client.py
   ```

The client first invokes `workflows-store-credentials` with the provided token and
then calls the `github_org_search` workflow, which uses the cached token to
query the GitHub MCP server.
