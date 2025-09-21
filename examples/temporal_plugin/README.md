# MCP-Agent with Temporal Plugin

This example demonstrates multiple ways to use the Temporal plugin with MCP-Agent for workflow orchestration.

## Prerequisites

1. **Temporal Server**: Ensure you have a Temporal server running locally:
   ```bash
   temporal server start-dev
   ```
   This starts a development server at `localhost:7233`

2. **API Keys**: Add your API keys to `mcp_agent.secrets.yaml`:
   ```yaml
   OPENAI_API_KEY: "your-key-here"
   ANTHROPIC_API_KEY: "your-key-here"  # optional
   ```

3. **Configuration**: Set the execution engine to `temporal` in `mcp_agent.config.yaml`:
   ```yaml
   execution_engine: temporal

   temporal:
     host: "localhost:7233"
     namespace: "default"
     task_queue: "mcp-agent"
   ```

## Usage Methods

### Method 1: Separate Worker and Workflow Files

This approach separates the worker and workflow execution into different processes, useful for distributed systems.

**Step 1: Define your workflow** (`basic_workflow.py`):
```python
from temporalio import workflow
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

@workflow.defn
class BasicWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        simple_agent = Agent(
            name="finder",
            instruction="You are a helpful agent",
            server_names=["fetch"],
        )

        async with simple_agent:
            llm = await simple_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(prompt)
            return result
```

**Step 2: Run the worker** (`run_worker.py`):
```bash
uv run run_worker.py
```

**Step 3: Execute the workflow** (in another terminal):
```bash
uv run run_basic_workflow.py
```

### Method 2: Single File Execution (temporal_agent.py)

This approach combines worker and workflow execution in a single file, ideal for simpler deployments or testing.

```bash
uv run temporal_agent.py
```

This file:
- Defines the workflow
- Starts the worker
- Executes the workflow
- All within the same process using `async with Worker(...)`

**Key difference**: The single-file approach runs both the worker and client in the same process:
```python
async with Worker(
    client,
    task_queue=running_app.config.temporal.task_queue,
    workflows=[BasicWorkflow],
):
    # Execute workflow while worker is running
    output = await client.execute_workflow(...)
```

## Important Configuration Notes

### Execution Engine Setting

The `execution_engine` in `mcp_agent.config.yaml` **MUST** be set to `temporal` for the Temporal plugin to work:

```yaml
execution_engine: temporal  # Required for Temporal plugin
```

Without this setting, MCP-Agent will use the default `asyncio` engine and Temporal features won't be available.

### Temporal Configuration

Configure Temporal settings in `mcp_agent.config.yaml`:

```yaml
temporal:
  host: "localhost:7233"           # Temporal server address
  namespace: "default"              # Temporal namespace
  task_queue: "mcp-agent"          # Task queue name
  max_concurrent_activities: 10    # Concurrency limit
  rpc_metadata:
    X-Client-Name: "mcp-agent"     # Client identification
```

## File Structure

```
temporal_plugin/
├── basic_workflow.py        # Workflow definition
├── run_worker.py           # Worker process (Method 1)
├── run_basic_workflow.py   # Workflow client (Method 1)
├── temporal_agent.py       # Single-file approach (Method 2)
├── main.py                 # MCP-Agent app setup
├── mcp_agent.config.yaml   # Configuration (MUST set execution_engine: temporal)
└── mcp_agent.secrets.yaml  # API keys
```

## When to Use Each Method

- **Separate Files (Method 1)**: Use when you need:
  - Distributed workers across multiple machines
  - Independent scaling of workers and clients
  - Clear separation of concerns
  - Production deployments

- **Single File (Method 2)**: Use when you need:
  - Quick prototyping and testing
  - Simple deployments
  - All-in-one execution for demos
  - Development and debugging

## Troubleshooting

1. **Temporal not working**: Ensure `execution_engine: temporal` in config
2. **Connection refused**: Start Temporal server with `temporal server start-dev`
3. **Task queue mismatch**: Verify task queue names match between worker and client

## Further Resources

- [Temporal Documentation](https://docs.temporal.io/)
- [MCP-Agent Documentation](https://docs.mcp-agent.com/)
- [MCP-Agent GitHub](https://github.com/lastmile-ai/mcp-agent)
