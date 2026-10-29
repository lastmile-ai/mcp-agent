# NVIDIA NIM Basic Agent Example

This example demonstrates using **NVIDIA NIM** with mcp-agent to run NVIDIA-hosted models (or a self-hosted NIM) with full tool calling and structured output support.

## Architecture

```plaintext
┌──────────────┐      ┌──────────────┐
│  NVIDIA      │──────▶│  Filesystem  │
│  Agent       │      │  MCP Server  │
└──────────────┘      └──────────────┘
       │
       │ OpenAI-compatible API
       ▼
┌──────────────────────────────┐
│  NVIDIA NIM                  │
│  https://integrate.api.      │
│  nvidia.com/v1               │
└──────────────────────────────┘
```

The agent uses the filesystem MCP server to read and analyze local files, with LLM inference served by NVIDIA NIM.

## Prerequisites

### 1. Get an NVIDIA API Key

Create an account and generate an API key at [https://build.nvidia.com](https://build.nvidia.com)

### 2. Set the API Key

```bash
export NVIDIA_API_KEY="<your-nvidia-api-key>"
```

### 3. (Optional) Use a Self-Hosted NIM

If you run NIM yourself, point the example at it by setting `base_url` under `nvidia` in `mcp_agent.config.yaml`, or:

```bash
export NVIDIA_BASE_URL="http://localhost:8000/v1"
```

## Setup

### 1. Clone and Navigate

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/nvidia
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

The example uses `mcp_agent.config.yaml` which is already configured for NVIDIA:

```yaml
nvidia:
  # base_url defaults to https://integrate.api.nvidia.com/v1
  # api_key is read from the NVIDIA_API_KEY environment variable
  default_model: "nvidia/nemotron-3.5-super-vl-120b-a12b"
```

You can also put the key in `mcp_agent.secrets.yaml` instead of the environment:

```yaml
nvidia:
  api_key: "<your-nvidia-api-key>"
```

## Running the Example

With `NVIDIA_API_KEY` set:

```bash
uv run main.py
```

## Expected Output

You should see output like:

```
INFO - Starting NVIDIA example...
INFO - NVIDIA config: {'base_url': 'https://integrate.api.nvidia.com/v1', 'default_model': 'nvidia/nemotron-3.5-super-vl-120b-a12b', ...}
INFO - Agent has 3 tools available: ['read_file', 'read_multiple_files', 'list_directory']

--- Example 1: Reading config file ---
INFO - Agent response: The mcp_agent.config.yaml file configures one MCP server: filesystem...

--- Example 2: Listing files ---
INFO - Agent response: Found 1 Python file in the current directory: main.py...

--- Example 3: Multi-turn conversation ---
INFO - Turn 1 response: The main Python file is main.py
INFO - Turn 2 response: This file demonstrates using NVIDIA NIM with mcp-agent...

--- Example completed successfully! ---
INFO - Token usage summary: {...}
```

## Switching to Other Models

You can use any chat model available to your key on [build.nvidia.com](https://build.nvidia.com), for example `nvidia/nemotron-3-ultra-550b-a55b` or `nvidia/nemotron-3.5-lightning-30b-a3b`. Just update `mcp_agent.config.yaml`:

```yaml
nvidia:
  default_model: "your-model-identifier"
```

## Additional Resources

- [NVIDIA NIM Documentation](https://docs.nvidia.com/nim/)
- [mcp-agent Documentation](https://docs.mcp-agent.com)
- [MCP Protocol](https://modelcontextprotocol.io)
