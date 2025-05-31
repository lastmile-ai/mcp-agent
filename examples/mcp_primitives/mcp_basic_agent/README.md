# MCP Primitives Example: Using Resources and Prompts

This example demonstrates how to use **MCP primitives**—specifically, **resources** and **prompts**—in an agent application. It shows how to connect to a custom MCP server that exposes structured resources and prompts, list and access those resources and prompts, and use them as context for an LLM-powered agent.

---

## What are MCP Primitives?

MCP (Model Context Protocol) primitives are standardized building blocks for agent applications. The two most important primitives are:

- **Resources**: Structured data (files, documents, datasets, status endpoints, etc.) exposed by an MCP server, accessible via URIs.
- **Prompts**: Standardized prompt templates that can be listed and invoked from an MCP server. Prompts can be parameterized and used as context or invoked directly.

This example demonstrates **both resources and prompts**.

---

## Example Overview

- **demo_server.py** implements a simple MCP server that exposes several resources and a prompt:
  - **Resources:**
    - `demo://docs/readme`: A sample README file (Markdown)
    - `demo://config/settings`: Example configuration settings (JSON)
    - `demo://data/users`: Example user data (JSON)
    - `demo://status/health`: Dynamic server health/status info (JSON)
  - **Prompt:**
    - `echo`: A simple prompt that echoes back the provided message

- **main.py** shows how to:
  1. Connect an agent to the demo MCP server
  2. List all available resources and prompts
  3. Attach a resource and a prompt to the agent
  4. Use an LLM (OpenAI) to summarize the content of the attached resources and prompts by passing them as context

---

## Architecture

```plaintext
┌────────────────────┐
│   demo_server      │
│   MCP Server       │
│ (resources, prompts)│
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  Agent (Python)    │
│  + LLM (OpenAI)    │
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
cd mcp-agent/examples/mcp_primitives/mcp_basic_agent
```

---

## 2. Run the Agent Example

Run the agent script which should auto install all necessary dependencies:

```bash
uv run main.py
```

You should see logs showing:
- The agent connecting to the demo server
- Listing available resources and prompts
- Attaching a resource and a prompt to the agent
- Using the LLM to summarize the content of the attached resources and prompts

---

## How it Works

- The agent connects to the demo MCP server and calls `list_resources()` and `list_prompts()` to discover available resources and prompts.
- It selects specific resource URIs (e.g., README) and prompt names (e.g., `echo`), and attaches them to itself.
- The agent can invoke a prompt with parameters (e.g., `echo` with a message).
- The LLM receives the actual content of those resources and prompts and generates a summary.

---

## Extending

You can add your own resources or prompts to `demo_server.py` using the `@mcp.resource` and `@mcp.prompt` decorators. Any function can expose a resource (static or dynamic) or a prompt.

---

## References

- [Model Context Protocol (MCP) Introduction](https://modelcontextprotocol.io/introduction)
- [MCP Agent Framework](https://github.com/lastmile-ai/mcp-agent)
- [MCP Server Primitives](https://modelcontextprotocol.io/specification#primitives)

---

This example is a minimal, practical demonstration of how to use **MCP resources and prompts** as first-class context for agent applications.
