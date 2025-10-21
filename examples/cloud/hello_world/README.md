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

The `deploy` command will bundle the app files and deploy them, producing a server URL like the following:
`https://17tp6d6s3l6zcq9oy1441nzlpo7a8gb9.deployments.mcp-agent.com`.

## Test

Use MCP Inspector to explore and test this server:

```bash
npx @modelcontextprotocol/inspector
```

Make sure to fill out the following settings:

| Setting          | Value                                                                           |
| ---------------- | ------------------------------------------------------------------------------- |
| _Transport Type_ | _SSE_                                                                           |
| _SSE_            | _https://[your-agent-server-id].deployments.mcp-agent-cloud.lastmileai.dev/sse_ |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.
