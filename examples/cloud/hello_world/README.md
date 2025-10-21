# Hello World Example

This example shows a very basic app with a `hello_world` tool call.

## Set up

First, clone the repo and navigate to this example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/cloud/hello_world
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

## Deploy

```bash
uv run mcp-agent deploy hello-world --no-auth
```

Note the use of `--no-auth` flag here will allow unauthenticated access to this server using its URL.

The `deploy` command will bundle the app files and deploy them, producing a server URL:
`https://<server_id>.deployments.mcp-agent.com`.

## Test

Use MCP Inspector to explore and test this server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

Make sure Inspector is configured with the following settings:

| Setting          | Value                                                                |
| ---------------- | -------------------------------------------------------------------- |
| _Transport Type_ | _SSE_                                                                |
| _SSE_            | _https://[server_id].deployments.mcp-agent-cloud.lastmileai.dev/sse_ |

In MCP Inspector, click Tools > List Tools to view the tools available on the server.
There are a number of default tools for interacting with workflows. There will also be a `hello_world` tool in the list. Select it and then click the 'Run Tool' button to run it. The result will show a `run_id` which can be used as input to the `workflows-get_status` tool to get the status (and result) of the workflow run for the `hello_world` tool.
