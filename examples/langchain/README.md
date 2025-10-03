# Third-Party Tools Integration Example

This example demonstrates seamlessly integrating tools from other AI Agent frameworks like CrewAI and LangChain into MCP Agent. This interoperability is crucial because it allows for faster development time and lets you reuse existing tools from the broader AI ecosystem.

In this example, we show how to use a LangChain tool (Serper API for web search) within an MCP Agent workflow.


## App Setup

Clone the repo and navigate to the third-party tools example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/langchain
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync --extra langchain
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## Set up Serper API Key

Create a `.env` file in this directory with your API key:

```bash
# Serper API Key (for web search)
SERPER_API_KEY=your_serper_api_key_here
```

You can get a Serper API key from [serper.dev](https://serper.dev/).

## Run the Example

Run your MCP Agent app:

```bash
uv run main.py
```