# Dreamtune MCP tools

Connect an MCP Agent `Agent` to [Dreamtune](https://dreamtunelabs.com) for model APIs, tools, GPU compute and run inspection. This example uses the published stdio server, so it needs no additional LLM provider key.

## Setup

Install Python 3.10+, [uv](https://docs.astral.sh/uv/) and Node.js **22.20+** with `npx` on your PATH. From the repository root:

```sh
uv sync --frozen --group dev
cd examples/mcp/dreamtune
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
```

Put your Dreamtune workspace API key in `mcp_agent.secrets.yaml`. The repository ignores this private file. MCP Agent merges it with `mcp_agent.config.yaml`; the origin and request timeout remain in the public configuration. The SDK package version is pinned in the server arguments.

On PowerShell, use `Copy-Item` instead of `cp` if preferred. Start Python from a terminal where Node and `npx` can be resolved.

## Discover tools

```sh
uv run main.py
```

The default run initializes the MCP connection, prints tool names and descriptions, then closes it. It does not execute a model, a tool run or a compute job. An `Agent` can use the same `server_names=["dreamtune"]` alongside other MCP servers.

## Call a tool explicitly

Use a name printed by discovery and the JSON arguments from the [MCP tool reference](https://docs.dreamtunelabs.com/reference/mcp-tools):

```sh
uv run main.py --tool dreamtune_compute_catalog --arguments '{}'
```

The result is printed as JSON; MCP tool errors return a nonzero exit status. Calls use your key's scopes and workspace. Model runs, paid tool runs and compute jobs can incur charges; compute may continue billing until stopped. The example only invokes a tool when `--tool` is supplied.

See [local MCP setup](https://docs.dreamtunelabs.com/connect/local-mcp) for optional GPU access and [hosted MCP setup](https://docs.dreamtunelabs.com/connect/mcp) for Streamable HTTP clients.
