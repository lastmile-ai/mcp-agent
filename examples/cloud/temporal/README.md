# MCP Agent Server Example (Temporal)

This example demonstrates how to create an MCP Agent Server with durable execution using [Temporal](https://temporal.io/). It shows how to build, run, deploy and connect to an MCP server which leverages Temporal workflows for execution.

## Motivation

When an mcp-agent server is deployed to the cloud, execution will be backed by Temporal workflow runs. Aside from `@app.tool` and `@app.async_tool` decorators (which implicitly create workflow runs in the cloud), mcp-agent also supports explicit Workflow and WorkflowRun definitions.

The main advantages of using Temporal are:

- **Durable execution** - Workflows can be long-running, paused, resumed, and retried
- **Visibility** - Monitor and debug workflows using the Temporal Web UI
- **Scalability** - Distribute workflow execution across multiple workers
- **Recovery** - Automatic retry and recovery from failures

Temporal provides these features out-of-the-box and is recommended for production deployments.

## Concepts Demonstrated

- Creating workflows with the `Workflow` base class
- Registering workflows with an `MCPApp`
- Workflow signals and durable execution

## Components in this Example

1. **BasicAgentWorkflow**: A simple workflow that demonstrates basic agent functionality:

   - Creates an agent with access to fetch and filesystem
   - Uses OpenAI's LLM to process input
   - Standard workflow execution pattern
   - Specify run_parameters as: `{"input": "Your input"}`

2. **PauseResumeWorkflow**: A workflow that demonstrates Temporal's signaling capabilities:
   - Starts a workflow and pauses execution awaiting a signal
   - Shows how workflows can be suspended and resumed
   - Demonstrates Temporal's durable execution pattern
   - Specify run_parameters as: `{"input": "Your input"}`
   - Resume with `workflows-resume` tool, specifying the run_id and payload `{}`

## Available Endpoints

The MCP agent server exposes the following tools:

- `workflows-list` - Lists all available workflows
- `workflows-BasicAgentWorkflow-run` - Runs the BasicAgentWorkflow, returns the workflow run ID
- `workflows--get_status` - Gets the status of a running workflow
- `workflows-PauseResumeWorkflow-run` - Runs the PauseResumeWorkflow, returns the workflow run ID
- `workflows-resume` - Sends a signal to resume a workflow that's waiting
- `workflows-cancel` - Cancels a running workflow

## Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv) package manager
- API key for OpenAI
- Temporal server for local testing (see setup instructions below)

## Configuration

To run or deploy the example, you'll need to configure the necessary paths and API keys.

### API Keys

1. Copy the example secrets file:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

2. Edit `mcp_agent.secrets.yaml` to add your API key:

```yaml
openai:
  api_key: "your-openai-api-key"
```

The provided `mcp_agent.config.yaml` already targets the local Temporal dev server. If you register additional `@workflow_task` activities in your own modules, uncomment the top-level `workflow_task_modules` list in that file and add your module paths so the worker imports them at startup.

## Test Locally

Before running this example, you need to have a Temporal server running:

1. Install the Temporal CLI by following the instructions at: https://docs.temporal.io/cli/

2. In a separate terminal, start a local Temporal server:

```bash
temporal server start-dev
```

This will start a Temporal server on `localhost:7233` (the default address configured in `mcp_agent.config.yaml`).

You can use the Temporal Web UI to monitor your workflows by visiting `http://localhost:8233` in your browser.

In a second terminal:

Install the required dependencies:

```bash
cd examples/cloud/temporal
uv pip install -r requirements.txt
```

Start the temporal worker:

```bash
uv run temporal_worker.py
```

Start the MCP server:

```bash
uv run main.py
```

Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test the server:

```bash
npx @modelcontextprotocol/inspector --transport sse --server-url http://127.0.0.1:8000/sse
```

## Advanced Features with Temporal

### Workflow Signals

This example demonstrates how to use Temporal workflow signals for coordination with the PauseResumeWorkflow:

1. Run the PauseResumeWorkflow using the `workflows-PauseResumeWorkflow-run` tool
2. The workflow will pause and wait for a "resume" signal
3. Send the signal in one of two ways:
   - Using the `workflows-resume` tool with the workflow ID and run ID
   - Using the Temporal UI to send a signal manually
4. After receiving the signal, the workflow will continue execution

### Monitoring Local Workflows

You can monitor all running workflows using the Temporal Web UI:

1. Open `http://localhost:8233` in your browser
2. Navigate to the "Workflows" section
3. You'll see a list of all workflow executions, their status, and other details
4. Click on a workflow to see its details, history, and to send signals

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
uv run mcp-agent deploy temporal_example
```

5. In the terminal, you will then be prompted to specify the type of secret to save your OpenAI API key as. Select (1) deployment secret so that it is available to the deployed server.

The `deploy` command will bundle the app files and deploy them, producing a server URL of the form:
`https://<server_id>.deployments.mcp-agent.com`.

## MCP Clients

Since the mcp-agent app is exposed as an MCP server, it can be used in any MCP client just like any other MCP server.

### MCP Inspector

Use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to explore and test this server:

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

## Code Structure

- `main.py` - Defines the workflows and creates the MCP server
- `temporal_worker.py` - For local testing only. Sets up a Temporal worker to process local workflow tasks
- `mcp_agent.config.yaml` - Configuration for MCP servers and the Temporal execution engine
- `mcp_agent.secrets.yaml` - Contains API keys (not included in repository)
