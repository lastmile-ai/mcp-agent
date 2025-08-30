# MCP Sampling Example

This example demonstrates how to use **MCP sampling** in an agent application. 
It shows how to connect to an MCP server that exposes a tool that uses a sampling request to generate a response.

---

## What is MCP sampling?
Sampling in MCP allows servers to implement agentic behaviors, by enabling LLM calls to occur nested inside other MCP server features.
Following the MCP recommendations, users are prompted to approve sampling requests, as well as the output produced by the LLM for the sampling request.
More details can be found in the [MCP documentation](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling).

This example demonstrates sampling using [MCP agent servers](https://github.com/lastmile-ai/mcp-agent/blob/main/examples/mcp_agent_server/README.md).
It is also possible to use sampling when explicitly creating an MCP client. The code for that would look like the following: 

```python
settings = ... # MCP agent configuration
registry = ServerRegistry(settings)

@mcp.tool()
async def my_tool(input: str, ctx: Context) -> str:
    async with gen_client("my_server", registry, upstream_session=ctx.session) as my_client:
        result = await my_client.call_tool("some_tool", {"input": input})
        ... # etc
```

---

## Example Overview

- **nested_server.py** implements a simple MCP server that uses sampling to generate a haiku about a given topic
- **demo_server.py** implements a simple MCP server that implements an agent generating haikus using the tool exposed by `nested_server.py`
- **main.py** shows how to:
  1. Connect an agent to the demo MCP server, and then
  2. Invoke the agent implemented by the demo MCP server, thereby triggering a sampling request.

---

## Architecture

```plaintext
┌────────────────────┐
│   nested_server    │──────┐
│   MCP Server       │      │
└─────────┬──────────┘      │
          │                 │
          ▼                 │
┌────────────────────┐      │
│   demo_server      │      │
│   MCP Server       │      │
└─────────┬──────────┘      │
          │            sampling, via user approval
          ▼                 │
┌────────────────────┐      │
│  Agent (Python)    │      │      
│  + LLM (OpenAI)    │◀─────┘
└─────────┬──────────┘
          │
          ▼
   [User/Developer]
```

---

## 1. Setup

Clone the repo and navigate to this example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/mcp/mcp_sampling
```

---

## 2. Run the Agent Example

Run the agent script which should auto install all necessary dependencies:

```bash
uv run main.py
```

You should see logs showing:

- The agent connecting to the demo server, and calling the tool
- A request to approve the sampling request; type `approve` to approve (anything else will deny the request)
- A request to approve the result of the sampling request
- The final result of the tool call

---

## References

- [Model Context Protocol (MCP) Introduction](https://modelcontextprotocol.io/introduction)
- [MCP Agent Framework](https://github.com/lastmile-ai/mcp-agent)
- [MCP Server Sampling](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling)

---

This example is a minimal, practical demonstration of how to use **MCP sampling** as first-class context for agent applications.
