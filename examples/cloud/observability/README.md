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

## Test Locally

Install the dependencies:

```bash
uv pip install -r requirements.txt
```

Spin up the mcp-agent server locally with SSE transport:

```bash
uv run main.py
```

Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test the server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
```

In MCP Inspector, click Tools > List Tools to view the tools available on the server.
There are a number of default tools for interacting with workflows. There will also be `hello_world` and `hello_world_async` tools in the list.

Select `hello_world` and run it. The result will show immediately.

Run the `hello_world_async` tool and see that the tool result contains a workflow `run_id` which can be used as input to the `workflows-get_status` tool to get the status (and result) of the workflow run.

## Deploy to mcp-agent cloud

You can deploy this MCP-Agent app as a hosted mcp-agent app in the Cloud.

1. In your terminal, authenticate into mcp-agent cloud by running:

```bash
uv run mcp-agent login
```

2. You will be redirected to the login page, create an mcp-agent cloud account through Google or Github

3. Set up your mcp-agent cloud API Key and copy & paste it into your terminal

```
andrew_lm@Mac sdk-cloud % uv run mcp-agent login
INFO: Directing to MCP Agent Cloud API login...
Please enter your API key 🔑:
```

4. In your terminal, deploy the MCP app:

```bash
uv run mcp-agent deploy hello-world --no-auth
```

Note the use of `--no-auth` flag here will allow unauthenticated access to this server using its URL.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just
like any other MCP server.

## Test Deployment

Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test this server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

Make sure Inspector is configured with the following settings:

| Setting          | Value                                               |
| ---------------- | --------------------------------------------------- |
| _Transport Type_ | _SSE_                                               |
| _SSE_            | _https://[server_id].deployments.mcp-agent.com/sse_ |
| _Header Name_    | _Authorization_                                     |
| _Bearer Token_   | _your-mcp-agent-cloud-api-token_                    |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.
