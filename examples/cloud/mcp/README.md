# MCP Server Example

This example is an mcp-agent application that showcases how mcp-agent supports the following MCP primitives:

- Tools:
  - Creating workflows with the `Workflow` base class
  - Registering workflows with an `MCPApp`
  - Preferred: Declaring MCP tools with `@app.tool` and `@app.async_tool`
- Sampling
- Elicitation
- Notifications
- Prompts
- Resources
- Logging

# Tools (workflows and tool decorators)

## Workflows

Define workflows with `@app.workflow` and `@app.workflow_run` decorators; a `workflows-WorkflowName-run` tool will be generated for the run implementation.

## Preferred: Define tools with decorators

You can also declare tools directly from plain Python functions using `@app.tool` (sync) and `@app.async_tool` (async). This is the simplest and recommended way to expose agent logic.

```python
from mcp_agent.app import MCPApp
from typing import Optional

app = MCPApp(name="basic_agent_server")

# Synchronous tool – returns the final result to the caller
@app.tool
async def grade_story(story: str, app_ctx: Optional[Context] = None) -> str:
    """
    Grade a student's short story and return a structured report.
    """
    # ... implement using your agents/LLMs ...
    return "Report..."

# Asynchronous tool – starts a workflow and returns IDs to poll later
@app.async_tool(name="grade_story_async")
async def grade_story_async(story: str, app_ctx: Optional[Context] = None) -> str:
    """
    Start grading the story asynchronously.

    This tool starts the workflow and returns 'workflow_id' and 'run_id'. Use the
    generic 'workflows-get_status' tool with the returned IDs to retrieve status/results.
    """
    # ... implement using your agents/LLMs ...
    return "(async run)"
```

What gets exposed:

- Sync tools appear as `<tool_name>` and return the final result (no status polling needed).
- Async tools appear as `<tool_name>` and return `{"workflow_id","run_id"}`; use `workflows-get_status` to query status.

These decorator-based tools are registered automatically when you call `create_mcp_server_for_app(app)`.

The MCP agent server will also expose the following tools:

- `workflows-list` - Lists available workflows and their parameter schemas
- `workflows-get_status` - Get status for a running workflow by `run_id` (and optional `workflow_id`)
- `workflows-cancel` - Cancel a running workflow

If you use the preferred decorator approach:

- Sync tool: `grade_story` (returns final result)
- Async tool: `grade_story_async` (returns `workflow_id/run_id`; poll with `workflows-get_status`)

The workflow-based endpoints (e.g., `workflows-<Workflow>-run`) are still available when you define explicit workflow classes.

# Sampling

To perform sampling, send a SamplingMessage to the context's upstream session.

# Elicitation

Similar to sampling, elicitation can be done by sending an elicitation message to the upstream session via `context.upstream_session.elicit`.

# Notifications

Notifications can be sent to upstream sessions and clients using the app context.

# Prompts and Resources

The MCPApp can take an existing FastMCP server in its constructor and will use this FastMCP server as the underlying server implementation. The FastMCP server can be customized using the `@mcp.prompt()` and `@mcp.resource()` decorators to add custom prompts and resources.

# Logging

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- API key for OpenAI

## Configuration

Before running the example, you'll need to configure the necessary paths and API key.

### API Keys

1. Copy the example secrets file:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

2. Edit `mcp_agent.secrets.yaml` to add your API keys:

```yaml
openai:
  api_key: "your-openai-api-key"
```

## Test Locally

Install the dependencies:

```bash
cd examples/cloud/mcp
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

## Deploy to mcp-agent Cloud

You can deploy this MCP-Agent app as a hosted mcp-agent app in the Cloud.

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
uv run mcp-agent deploy mcp_agent_server
```

5. In the terminal, you will then be prompted to specify the type of secret to save your OpenAI API key as. Select (1) deployment secret so that it is available to the deployed server.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just
like any other MCP server.

### MCP Inspector

You can inspect and test the server using [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url https://<server_id>.deployments.mcp-agent.com/sse
```

This will launch the MCP Inspector UI where you can:

- See all available tools
- Test workflow execution
- View request/response details

Make sure Inspector is configured with the following settings:

| Setting          | Value                                               |
| ---------------- | --------------------------------------------------- |
| _Transport Type_ | _SSE_                                               |
| _SSE_            | _https://[server_id].deployments.mcp-agent.com/sse_ |
| _Header Name_    | _Authorization_                                     |
| _Bearer Token_   | _your-mcp-agent-cloud-api-token_                    |

> [!TIP]
> In the Configuration, change the request timeout to a longer time period. Since your agents are making LLM calls, it is expected that it should take longer than simple API calls.
