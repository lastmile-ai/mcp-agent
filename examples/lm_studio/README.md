# LM Studio Basic Agent Example

This example demonstrates using **LM Studio** with mcp-agent to run local LLMs with full tool calling and structured output support.

## Architecture

```plaintext
┌──────────────┐      ┌──────────────┐
│  LM Studio   │──────▶│  Filesystem  │
│  Agent       │      │  MCP Server  │
└──────────────┘      └──────────────┘
       │
       │ OpenAI-compatible API
       ▼
┌──────────────┐
│  LM Studio   │
│  Local       │
│  http://     │
│  localhost   │
│  :1234       │
└──────────────┘
```

The agent uses the filesystem MCP server to read and analyze local files, with all LLM inference happening locally through LM Studio.

## Prerequisites

### 1. Install LM Studio

Download and install LM Studio from [https://lmstudio.ai](https://lmstudio.ai)

### 2. Download and Load a Model

1. Open LM Studio
2. Go to the "Search" tab
3. Search for and download: **`openai/gpt-oss-20b`**
4. Once downloaded, go to the "Chat" tab
5. Load the model by selecting it from the dropdown

### 3. Start the LM Studio Server

1. In LM Studio, go to the "Developer" tab (or "Local Server" section)
2. Click "Start Server"
3. The server should start at `http://localhost:1234`
4. Verify it's running by visiting `http://localhost:1234/v1/models` in your browser

## Setup

### 1. Clone and Navigate

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/lm_studio
```

### 2. Install Dependencies

Install `uv` (if you don't have it):

```bash
pip install uv
```

Install dependencies:

```bash
uv pip install -r requirements.txt
```

### 3. Configuration

The example uses `mcp_agent.config.yaml` which is already configured for LM Studio:

```yaml
lm_studio:
  # base_url defaults to http://localhost:1234/v1
  default_model: "openai/gpt-oss-20b"
```

**No API keys needed!** LM Studio runs locally and doesn't require authentication.

## Running the Example

With LM Studio running and the model loaded:

```bash
uv run main.py
```

## Expected Output

You should see output like:

```
INFO - Starting LM Studio example...
INFO - LM Studio config: {'api_key': 'lm-studio', 'base_url': 'http://localhost:1234/v1', 'default_model': 'openai/gpt-oss-20b'}
INFO - Agent has 3 tools available: ['read_file', 'read_multiple_files', 'list_directory']

--- Example 1: Reading config file ---
INFO - Agent response: The mcp_agent.config.yaml file configures one MCP server: filesystem...

--- Example 2: Listing files ---
INFO - Agent response: Found 1 Python file in the current directory: main.py...

--- Example 3: Multi-turn conversation ---
INFO - Turn 1 response: The main Python file is main.py
INFO - Turn 2 response: This file demonstrates using LM Studio with mcp-agent...

--- Example completed successfully! ---
INFO - Token usage summary: {...}
```

## Switching to Other Models

You can use any model loaded in LM Studio. Just update `mcp_agent.config.yaml`:

```yaml
lm_studio:
  default_model: "your-model-identifier"
```

## Additional Resources

- [LM Studio Documentation](https://lmstudio.ai/docs)
- [mcp-agent Documentation](https://docs.mcp-agent.com)
- [MCP Protocol](https://modelcontextprotocol.io)
