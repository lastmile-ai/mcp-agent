# MCP Agent Server Example (Asyncio)

This example is an mcp-agent application that is exposed as an MCP server, aka the "MCP Agent Server".

The MCP Agent Server exposes agentic workflows as MCP tools.

It shows how to build, run, and connect to an MCP server using the asyncio execution engine.

https://github.com/user-attachments/assets/f651af86-222d-4df0-8241-616414df66e4

## Concepts Demonstrated

- Creating workflows with the `Workflow` base class
- Registering workflows with an `MCPApp`
- Exposing workflows as MCP tools using `create_mcp_server_for_app`, optionally using custom FastMCP settings
- Connecting to an MCP server using `gen_client`
- Running workflows remotely and monitoring their status

## Components in this Example

1. **BasicAgentWorkflow**: A simple workflow that demonstrates basic agent functionality:

   - Connects to external servers (fetch, filesystem)
   - Uses LLMs (Anthropic Claude) to process input
   - Supports multi-turn conversations
   - Demonstrates model preference configuration

2. **ParallelWorkflow**: A more complex workflow that shows parallel agent execution:
   - Uses multiple specialized agents (proofreader, fact checker, style enforcer)
   - Processes content using a fan-in/fan-out pattern
   - Aggregates results into a final report

## Available Endpoints

The MCP agent server exposes the following tools:

- `workflows-list` - Lists all available workflows
- `workflows-BasicAgentWorkflow-run` - Runs the BasicAgentWorkflow, returns the wf run ID
- `workflows-BasicAgentWorkflow-get_status` - Gets the status of a running workflow
- `workflows-ParallelWorkflow-run` - Runs the ParallelWorkflow, returns the wf run ID
- `workflows-ParallelWorkflow-get_status` - Gets the status of a running workflow
- `workflows-cancel` - Cancels a running workflow

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- API keys for Anthropic and OpenAI

## Configuration

Before running the example, you'll need to configure the necessary paths and API keys.

### API Keys

1. Copy the example secrets file:

   ```bash
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   ```

2. Edit `mcp_agent.secrets.yaml` to add your API keys:
   ```yaml
   anthropic:
     api_key: "your-anthropic-api-key"
   openai:
     api_key: "your-openai-api-key"
   ```

## How to Run

### Using the Client Script

The simplest way to run the example is using the provided client script:

```bash
# Make sure you're in the mcp_agent_server/asyncio directory
uv run client.py
```

This will:

1. Start the basic_agent_server.py as a subprocess
2. Connect to the server
3. Run the BasicAgentWorkflow
4. Monitor and display the workflow status

### Running the Server and Client Separately

You can also run the server and client separately:

1. In one terminal, start the server:

   ```bash
   uv run basic_agent_server.py

   # Optionally, run with the example custom FastMCP settings
   uv run basic_agent_server.py --custom-fastmcp-settings
   ```

2. In another terminal, run the client:

   ```bash
   uv run client.py

   # Optionally, run with the example custom FastMCP settings
   uv run client.py --custom-fastmcp-settings
   ```

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just
like any other MCP server.

### MCP Inspector

You can inspect and test the server using [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector \
  uv \
  --directory /path/to/mcp-agent/examples/mcp_agent_server/asyncio \
  run \
  basic_agent_server.py
```

This will launch the MCP Inspector UI where you can:

- See all available tools
- Test workflow execution
- View request/response details

### Claude Desktop

To use this server with Claude Desktop:

1. Locate your Claude Desktop configuration file (usually in `~/.claude-desktop/config.json`)

2. Add a new server configuration:

   ```json
   "basic-agent-server": {
     "command": "/path/to/uv",
     "args": [
       "--directory",
       "/path/to/mcp-agent/examples/mcp_agent_server/asyncio",
       "run",
       "basic_agent_server.py"
     ]
   }
   ```

3. Restart Claude Desktop, and you'll see the server available in the tool drawer

4. (**claude desktop workaround**) Update `mcp_agent.config.yaml` file with the full paths to npx/uvx on your system:

   Find the full paths to `uvx` and `npx` on your system:

   ```bash
   which uvx
   which npx
   ```

   Update the `mcp_agent.config.yaml` file with these paths:

   ```yaml
   mcp:
     servers:
       fetch:
         command: "/full/path/to/uvx" # Replace with your path
         args: ["mcp-server-fetch"]
       filesystem:
         command: "/full/path/to/npx" # Replace with your path
         args: ["-y", "@modelcontextprotocol/server-filesystem"]
   ```

## Code Structure

- `basic_agent_server.py` - Defines the workflows and creates the MCP server
- `client.py` - Example client that connects to the server and runs workflows
- `mcp_agent.config.yaml` - Configuration for MCP servers and execution engine
- `mcp_agent.secrets.yaml` - Contains API keys (not included in repository)
- `short_story.md` - Sample content for testing the ParallelWorkflow

## Understanding the Workflow System

### Workflow Definition

Workflows are defined by subclassing the `Workflow` base class and implementing the `run` method:

```python
@app.workflow
class BasicAgentWorkflow(Workflow[str]):
    @app.workflow_run
    async def run(self, input: str) -> WorkflowResult[str]:
        # Workflow implementation...
        return WorkflowResult(value=result)
```

### Server Creation

The server is created using the `create_mcp_server_for_app` function:

```python
mcp_server = create_mcp_server_for_app(agent_app)
await mcp_server.run_stdio_async()
```

Similarly, you can launch the server over SSE, Websocket or Streamable HTTP transports.

### Client Connection

The client connects to the server using the `gen_client` function:

```python
async with gen_client("basic_agent_server", context.server_registry) as server:
    # Call server tools
    workflows_response = await server.call_tool("workflows-list", {})
    run_result = await server.call_tool(
        "workflows-BasicAgentWorkflow-run",
        arguments={"run_parameters": {"input": "..."}}
    )
```
