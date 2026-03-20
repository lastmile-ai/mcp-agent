# AG2 Tools Integration Example

This example demonstrates integrating tools from the AG2 (formerly AutoGen) framework
into MCP Agent. Similar to the LangChain and CrewAI examples, this shows how to reuse
existing tools from the broader AI ecosystem.

In this example, we use AG2's DuckDuckGo search tool within an MCP Agent workflow.
No additional API keys are needed beyond OpenAI — DuckDuckGo search is free and keyless.

## App Setup

Clone the repo and navigate to the AG2 example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/ag2
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync --extra ag2
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## Set up API Keys

Create a `.env` file in this directory with your OpenAI API key:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

## Run the Example

Run your MCP Agent app:

```bash
uv run main.py
```
