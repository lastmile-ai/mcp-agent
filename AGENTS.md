# mcp-agent — Notes for AI Contributors

This file contains quick-reference information for agents (and humans) contributing to [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent), a simple, composable framework for building agents with the Model Context Protocol (MCP).

## Project Overview

`mcp-agent` fully implements MCP and provides reusable patterns for building effective agents. It supports local development and durable execution backed by [Temporal](https://temporal.io/).

Key directories:

| Path | Purpose |
|------|---------|
| `src/mcp_agent/` | Core SDK source |
| `examples/` | Example applications (basic, MCP patterns, use cases, cloud, temporal) |
| `tests/` | Unit tests |
| `schema/` | JSON schema generated from `src/mcp_agent/config.py` |
| `scripts/` | Helper scripts, including `promptify.py` for LLM prompts |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python package management
- Python >= 3.10

## Development Commands

```bash
# Sync all dependencies (extras + dev)
make sync

# Format code
make format

# Lint and auto-fix
make lint

# Run tests
make tests

# Run tests with coverage
make coverage

# Regenerate JSON schema after config.py changes
make schema

# Generate LLM prompt file
make prompt
```

Lint and format are also run by the pre-commit hook defined in `.pre-commit-config.yaml`.

## Testing an Example

```bash
cd examples/basic/mcp_basic_agent
uv run main.py
```

Some examples require `mcp_agent.secrets.yaml` with API keys. Copy `mcp_agent.secrets.yaml.example` if present and fill in your credentials.

## Contribution Workflow

1. Fork the repo and create a feature branch prefixed with `feature/`.
2. Make focused changes.
3. Run `make lint` and `make tests`.
4. Add or update examples and tests for new functionality.
5. If you changed `src/mcp_agent/config.py`, run `make schema` and commit the updated schema file.
6. Open a pull request.

Reach out on [GitHub issues](https://github.com/lastmile-ai/mcp-agent/issues) or [Discord](https://lmai.link/discord/mcp-agent) before starting large contributions.

## Contribution Tips for Agents

- Keep PRs small and focused on one concern.
- Prefer adding/updating tests and examples for new features.
- Do not change public API signatures without updating examples and docs.
- Run the pre-commit hooks or `make lint` before pushing.
