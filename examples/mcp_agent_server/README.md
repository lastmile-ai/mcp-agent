# MCP Agent Server Examples

This directory contains examples of exposing MCP Agent workflows as MCP servers. It demonstrates how to build, launch, and interact with agent-powered MCP servers in different execution environments.

## Introduction

The MCP Agent Server pattern represents a significant evolution in agent architecture. While traditional MCP clients (like Claude, Cursor, VS Code) often act as agents consuming MCP server tools, these examples flip the paradigm:

- **Agents as Servers**: Package agent workflows into MCP servers
- **Agent Interoperability**: Enable multi-agent interactions through a standard protocol
- **Decoupled Architecture**: Separate agent logic from client interfaces

https://github.com/user-attachments/assets/f651af86-222d-4df0-8241-616414df66e4

## Why Expose Agents as MCP Servers?

1. **Agent Composition**: Build complex multi-agent systems where agents can interact with each other
2. **Platform Independence**: Use your agents from any MCP-compatible client
3. **Scalability**: Run agent workflows on dedicated infrastructure, not just within client environments
4. **Reusability**: Create agent workflows once, use them from multiple clients and environments
5. **Encapsulation**: Package complex agent logic into a well-defined, self-contained interface

## Execution Modes

This directory includes two implementations of the MCP Agent Server pattern:

### [Asyncio](./asyncio)

The asyncio implementation provides:

- In-memory execution with minimal setup
- Simple deployment with no external dependencies
- Fast startup and execution
- Great for development, testing, and less complex agent workflows

### [Temporal](./temporal)

The Temporal implementation provides:

- Durable execution of workflows using Temporal as the orchestration engine
- Pause/resume capabilities via Temporal signals
- Automatic retry and recovery from failures
- Workflow observability through the Temporal UI
- Ideal for production deployments and complex agent workflows

## Examples Overview

Each implementation demonstrates:

1. **BasicAgentWorkflow**: A simple agent workflow that processes input using LLMs
2. **ParallelWorkflow** (asyncio) or **PauseResumeWorkflow** (temporal): More complex patterns showing parallel execution or signaling capabilities

## Key MCP Agent Server Advantages

| Capability                   | Description                                                                        |
| ---------------------------- | ---------------------------------------------------------------------------------- |
| **Protocol Standardization** | Agents communicate via standardized MCP protocol, ensuring interoperability        |
| **Workflow Encapsulation**   | Complex agent workflows are exposed as simple MCP tools                            |
| **Execution Flexibility**    | Choose between in-memory (asyncio) or durable (Temporal) execution                 |
| **Client Independence**      | Connect from any MCP client: Claude, VSCode, Cursor, MCP Inspector, or custom apps |
| **Multi-Agent Ecosystems**   | Build systems where multiple agents can interact and collaborate                   |

## Getting Started

Each implementation directory contains its own README with detailed instructions. Prefer the decorator-based tool definition (`@app.tool` / `@app.async_tool`) for the simplest developer experience:

- [Asyncio Implementation](./asyncio/README.md)
- [Temporal Implementation](./temporal/README.md)

### Preferred: Declare tools with decorators

Instead of only defining workflow classes, you can expose tools directly from functions:

```python
from mcp_agent.app import MCPApp

app = MCPApp(name="my_agent_server")

@app.tool
async def do_something(arg: str) -> str:
    """Do something synchronously and return the final result."""
    return "done"

@app.async_tool(name="do_something_async")
async def do_something_async(arg: str) -> str:
    """
    Start work asynchronously.

    Returns 'workflow_id' and 'run_id'. Use 'workflows-get_status' with the returned
    IDs to retrieve status and results.
    """
    return "started"
```

- Sync tool returns the final result; no status polling needed.
- Async tool returns IDs for polling via the generic `workflows-get_status` endpoint.

## Multi-Agent Interaction Pattern

One of the most powerful capabilities enabled by the MCP Agent Server pattern is multi-agent interaction. Here's a conceptual example:

```
   ┌────────────────┐         ┌────────────────┐
   │                │         │                │
   │  Research      │  MCP    │  Writing       │
   │  Agent Server  │◄────────┤  Agent Server  │
   │                │         │                │
   └────────────────┘         └────────────────┘
           ▲                          ▲
           │                          │
           │                          │
           │     ┌────────────┐       │
           │     │            │       │
           └─────┤  Claude    ├───────┘
                 │  Desktop   │
                 │            │
                 └────────────┘
```

In this example:

1. Claude Desktop can use both agent servers
2. The Writing Agent can also use the Research Agent as a tool
3. All communication happens via the MCP protocol

## Integration Options

These examples show how to integrate MCP Agent Servers with various clients:

### Claude Desktop Integration

Configure Claude Desktop to access your agent servers by updating your `~/.claude-desktop/config.json`:

```json
"my-agent-server": {
  "command": "/path/to/uv",
  "args": [
    "--directory",
    "/path/to/mcp-agent/examples/mcp_agent_server/asyncio",
    "run",
    "basic_agent_server.py"
  ]
}
```

### MCP Inspector

Use MCP Inspector to explore and test your agent servers:

```bash
npx @modelcontextprotocol/inspector \
  uv \
  --directory /path/to/mcp-agent/examples/mcp_agent_server/asyncio \
  run \
  basic_agent_server.py
```

### Custom Clients

Build custom clients using the `gen_client` function:

```python
from mcp_agent.mcp.gen_client import gen_client

async with gen_client("basic_agent_server", context.server_registry) as server:
    # Call agent workflow tools
    result = await server.call_tool(
        "workflows-BasicAgentWorkflow-run",
        arguments={"run_parameters": {"input": "Your input here"}}
    )
```

## Additional Resources

- [MCP Agent Documentation](https://github.com/lastmile-ai/mcp-agent)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [Temporal Documentation](https://docs.temporal.io/) (for temporal implementation)
