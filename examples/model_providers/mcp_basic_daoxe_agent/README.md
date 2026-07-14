# MCP DaoXE Agent Example

This example runs the same "finder" Agent pattern against **DaoXE**, a multi-model multi-protocol API gateway, using mcp-agent's existing **OpenAI-compatible** client (`OpenAIAugmentedLLM`) and `base_url: https://daoxe.com/v1`.

DaoXE also exposes other protocol surfaces (for example OpenAI Responses and Anthropic Messages) for other clients; this example uses the Chat Completions path that mcp-agent's OpenAI integration already speaks.

**Notes**

- Model IDs are **account-scoped**. Use a model returned by authenticated `GET https://daoxe.com/v1/models` for your API key (or set `DAOXE_MODEL` / `openai.default_model`). Do not rely on a hardcoded public catalog.
- Service is **not available in mainland China**. See [DaoXE pricing / catalog](https://daoxe.com/pricing) and public starters: [seven7763/DaoXE-AI](https://github.com/seven7763/DaoXE-AI).

## `1` App set up

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/model_providers/mcp_basic_daoxe_agent
```

Install `uv` (if you don’t have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

## `2` Configure DaoXE

1. Create an API key at [https://daoxe.com](https://daoxe.com).
2. List models available to that key:

   ```bash
   curl -sS https://daoxe.com/v1/models \
     -H "Authorization: Bearer $DAOXE_API_KEY"
   ```

3. Copy secrets and set the key (and optionally a model):

   ```bash
   cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
   ```

   ```yaml
   # mcp_agent.secrets.yaml
   openai:
     api_key: "sk-..."   # your DaoXE key
     # default_model: "your-account-scoped-model-id"
   ```

   Or use environment variables:

   ```bash
   export OPENAI_API_KEY="sk-..."          # DaoXE API key
   export OPENAI_BASE_URL="https://daoxe.com/v1"
   export DAOXE_MODEL="your-account-scoped-model-id"
   ```

`mcp_agent.config.yaml` already points the OpenAI client at DaoXE:

```yaml
openai:
  base_url: "https://daoxe.com/v1"
```

## `3` Run locally

```bash
cd examples/model_providers/mcp_basic_daoxe_agent

export DAOXE_MODEL="your-account-scoped-model-id"  # from GET /v1/models
uv run main.py
```

## References

- [DaoXE](https://daoxe.com) / [pricing & catalog](https://daoxe.com/pricing)
- [DaoXE public examples](https://github.com/seven7763/DaoXE-AI)
- [mcp-agent configuration](https://docs.mcp-agent.com)
