# CrewAI Tools Integration Example

This example demonstrates how to integrate CrewAI tools into MCP Agent workflows. It shows how to use CrewAI's `SerperDevTool` for web search and `FileWriterTool` for file operations within an MCP Agent.

The example agent searches for information about Singapore's favorite dish and writes a haiku about it to a file.

## App Setup

Clone the repo and navigate to the CrewAI example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/crewai
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync --extra crewai
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## Set up Environment

Copy the example secrets file and add your API keys:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Edit `mcp_agent.secrets.yaml` to add your:
- OpenAI API key


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