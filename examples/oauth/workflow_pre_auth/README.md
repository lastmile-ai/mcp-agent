# Workflow Pre-Authorization Example

This example shows how to preload OAuth tokens for asynchronous workflows.
The client calls the `workflows-pre-auth` tool to store a token for a
specific workflow before the workflow runs. Once the token is saved, the
workflow can access the downstream MCP server without further user
interaction.

## Prerequisites

1. Obtain a GitHub access token (e.g., via the interactive example) and
   export it before running the client:

   ```bash
   export GITHUB_ACCESS_TOKEN="github_pat_xxx"
   ```

2. Install dependencies:

   ```bash
   pip install -e .
   # optional redis support
   # pip install -e .[redis]
   ```

3. (Optional) To persist tokens in Redis instead of memory, start a Redis
   instance and set `OAUTH_REDIS_URL`, for example:

   ```bash
   docker run --rm -p 6379:6379 redis:7-alpine
   export OAUTH_REDIS_URL="redis://127.0.0.1:6379"
   ```

## Running

1. Start the workflow server:

   ```bash
   python examples/oauth/workflow_pre_auth/main.py
   ```

2. In another terminal, run the client to seed the token and execute the
   workflow:

   ```bash
   python examples/oauth/workflow_pre_auth/client.py
   ```

The client first invokes `workflows-pre-auth` with the provided token and
then calls the `github_org_search` workflow, which uses the cached token to
query the GitHub MCP server.
