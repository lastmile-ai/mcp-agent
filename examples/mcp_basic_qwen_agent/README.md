# MCP Qwen Agent Example - "Finder" Agent

This example demonstrates how to create and run a basic "Finder" Agent using Qwen models via Ollama's OpenAI-compatible API and MCP. The Agent has access to both the `fetch` and `filesystem` MCP servers, enabling it to retrieve information from URLs and the local file system.

## Prerequisites

- [Ollama](https://ollama.ai/) installed and running
- Qwen model pulled in Ollama (run `ollama pull qwen2.5:32b`)

## Setup

Before running the agent, ensure you have Ollama installed and the Qwen models pulled:

```bash
# Install Ollama (Mac/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Start the Ollama service
ollama serve

# Pull the Qwen model (in another terminal)
ollama pull qwen2.5:32b
```
