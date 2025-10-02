# MCP Agent Server Example (Temporal)

This example demonstrates how to create an MCP Agent Server with durable execution using [Temporal](https://temporal.io/). It shows how to build, run, and connect to an MCP server that uses Temporal as the execution engine.

## Motivation

`mcp-agent` supports both `asyncio` and `temporal` execution modes. These can be configured by changing the `execution_engine` property in the `mcp_agent.config.yaml`.

The main advantages of using Temporal are:

- **Durable execution** - Workflows can be long-running, paused, resumed, and retried
- **Visibility** - Monitor and debug workflows using the Temporal Web UI
- **Scalability** - Distribute workflow execution across multiple workers
- **Recovery** - Automatic retry and recovery from failures

While similar capabilities can be implemented with asyncio in-memory execution, Temporal provides these features out-of-the-box and is recommended for production deployments.

## Concepts Demonstrated

- Creating workflows with the `Workflow` base class
- Registering workflows with an `MCPApp`
- Setting up a Temporal worker to process workflow tasks
- Exposing Temporal workflows as MCP tools using `create_mcp_server_for_app`
- Connecting to an MCP server using `gen_client`
- Workflow signals and durable execution

## Components in this Example

1. **BasicAgentWorkflow**: A simple workflow that demonstrates basic agent functionality:

   - Creates an agent with access to fetch and filesystem
   - Uses OpenAI's LLM to process input
   - Standard workflow execution pattern

2. **PauseResumeWorkflow**: A workflow that demonstrates Temporal's signaling capabilities:
   - Starts a workflow and pauses execution awaiting a signal
   - Shows how workflows can be suspended and resumed
   - Demonstrates Temporal's durable execution pattern

## Available Endpoints

The MCP agent server exposes the following tools:

- `workflows-list` - Lists all available workflows
- `workflows-BasicAgentWorkflow-run` - Runs the BasicAgentWorkflow, returns the workflow run ID
- `workflows-BasicAgentWorkflow-get_status` - Gets the status of a running workflow
- `workflows-PauseResumeWorkflow-run` - Runs the PauseResumeWorkflow, returns the workflow run ID
- `workflows-PauseResumeWorkflow-get_status` - Gets the status of a running workflow
- `workflows-resume` - Sends a signal to resume a workflow that's waiting
- `workflows-cancel` - Cancels a running workflow

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- API keys for Anthropic and OpenAI
- Temporal server (see setup instructions below)

## Setting Up Temporal Server

Before running this example, you need to have a Temporal server running:

1. Install the Temporal CLI by following the instructions at: https://docs.temporal.io/cli/

2. Start a local Temporal server:
   ```bash
   temporal server start-dev
   ```

This will start a Temporal server on `localhost:7233` (the default address configured in `mcp_agent.config.yaml`).

You can use the Temporal Web UI to monitor your workflows by visiting `http://localhost:8233` in your browser.

## Configuration

Before running the example, you'll need to configure the necessary paths and API keys.

### Path Configuration

The `mcp_agent.config.yaml` file contains paths to executables. For Claude Desktop integration, you may need to update these with the full paths on your system:

1. Find the full paths to `uvx` and `npx` on your system:

   ```bash
   which uvx
   which npx
   ```

2. Update the `mcp_agent.config.yaml` file with these paths:
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

To run this example, you'll need to:

1. Install the required dependencies:

   ```bash
   uv pip install -r requirements.txt
   ```

2. Start the Temporal server (as described above)

   ```bash
   temporal server start-dev
   ```

3. In a separate terminal, start the Temporal worker:

   ```bash
   uv run basic_agent_server_worker.py
   ```

   The worker will register the workflows with Temporal and wait for tasks to execute.

4. In another terminal, start the MCP server:

   ```bash
   uv run main.py
   ```

5. In a fourth terminal, run the client:
   ```bash
   uv run client.py
   ```

### Testing Specific Features

The Temporal client supports feature flags to exercise subsets of functionality. Available flags: `workflows`, `tools`, `sampling`, `elicitation`, `notifications`, or `all`.

Examples:

```bash
# Default (all features)
uv run client.py

# Only workflows
uv run client.py --features workflows

# Only tools
uv run client.py --features tools

# Sampling + elicitation workflows
uv run client.py --features sampling elicitation

# Only notifications-related workflow
uv run client.py --features notifications

# Increase server logging verbosity seen by the client
uv run client.py --server-log-level debug
```

Console output:

- Server logs appear as lines prefixed with `[SERVER LOG] ...`.
- Other server-originated notifications (e.g., `notifications/progress`, `notifications/resources/list_changed`) appear as `[SERVER NOTIFY] <method>: ...`.

## Advanced Features with Temporal

### Workflow Signals

This example demonstrates how to use Temporal workflow signals for coordination with the PauseResumeWorkflow:

1. Run the PauseResumeWorkflow using the `workflows-PauseResumeWorkflow-run` tool
2. The workflow will pause and wait for a "resume" signal
3. Send the signal in one of two ways:
   - Using the `workflows-resume` tool with the workflow ID and run ID
   - Using the Temporal UI to send a signal manually
4. After receiving the signal, the workflow will continue execution

### Monitoring Workflows

You can monitor all running workflows using the Temporal Web UI:

1. Open `http://localhost:8233` in your browser
2. Navigate to the "Workflows" section
3. You'll see a list of all workflow executions, their status, and other details
4. Click on a workflow to see its details, history, and to send signals

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just like any other MCP server.

### MCP Inspector

You can inspect and test the server using [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector \
  uv \
  --directory /path/to/mcp-agent/examples/mcp_agent_server/temporal \
  run \
  main.py
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
   "basic-agent-server-temporal": {
     "command": "/path/to/uv",
     "args": [
       "--directory",
       "/path/to/mcp-agent/examples/mcp_agent_server/temporal",
       "run",
       "main.py"
     ]
   }
   ```

3. Start the Temporal server and worker in separate terminals as described in the "How to Run" section

4. Restart Claude Desktop, and you'll see the server available in the tool drawer

## Code Structure

- `main.py` - Defines the workflows and creates the MCP server
- `basic_agent_server_worker.py` - Sets up the Temporal worker to process workflow tasks
- `client.py` - Example client that connects to the server and runs workflows
- `mcp_agent.config.yaml` - Configuration for MCP servers and the Temporal execution engine
- `mcp_agent.secrets.yaml` - Contains API keys (not included in repository)

## Understanding the Temporal Workflow System

### Workflow Definition

Workflows are defined by subclassing the `Workflow` base class and implementing the `run` method:

```python
@app.workflow
class PauseResumeWorkflow(Workflow[str]):
    @app.workflow_run
    async def run(self, message: str) -> WorkflowResult[str]:
        print(f"Starting PauseResumeWorkflow with message: {message}")
        print(f"Workflow is pausing, workflow_id: {self.id}, run_id: {self.run_id}")

        # Wait for the resume signal - this will pause the workflow
        await app.context.executor.wait_for_signal(
            signal_name="resume", workflow_id=self.id, run_id=self.run_id,
        )

        print("Signal received, workflow is resuming...")
        result = f"Workflow successfully resumed! Original message: {message}"
        return WorkflowResult(value=result)
```

### Worker Setup

The worker is set up in `basic_agent_server_worker.py` using the `create_temporal_worker_for_app` function:

```python
async def main():
    async with create_temporal_worker_for_app(app) as worker:
        await worker.run()
```

### Server Creation

The server is created using the `create_mcp_server_for_app` function:

```python
mcp_server = create_mcp_server_for_app(agent_app)
await mcp_server.run_sse_async()  # Using Server-Sent Events (SSE) for transport
```

### Client Connection

The client connects to the server using the `gen_client` function:

```python
async with gen_client("basic_agent_server", context.server_registry) as server:
    # Call the BasicAgentWorkflow
    run_result = await server.call_tool(
        "workflows-BasicAgentWorkflow-run",
        arguments={"run_parameters": {"input": "What is the Model Context Protocol?"}}
    )

    # Call the PauseResumeWorkflow
    pause_result = await server.call_tool(
        "workflows-PauseResumeWorkflow-run",
        arguments={"run_parameters": {"message": "Custom message for the workflow"}}
    )

    # The workflow will pause - to resume it, send the resume signal
    execution = WorkflowExecution(
      **json.loads(pause_result.content[0].text)
   )

   run_id = execution.run_id
   workflow_id = execution.workflow_id

    await server.call_tool(
        "workflows-resume",
        arguments={"workflow_id": workflow_id, "run_id": run_id}
    )
```

## Additional Resources

- [Temporal Documentation](https://docs.temporal.io/)
- [MCP Agent Documentation](https://github.com/lastmile-ai/mcp-agent)
- [Temporal Examples in mcp-agent](https://github.com/lastmile-ai/mcp-agent/tree/main/examples/temporal)
