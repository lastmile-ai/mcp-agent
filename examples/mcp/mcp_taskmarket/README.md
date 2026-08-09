# TaskMarket MCP Server Example

An MCP server that exposes [TaskMarket](https://taskmarket.dev/) (an on-chain
task marketplace on Base) as tools for `mcp-agent` workflows.

## What it does

The agent can:

- **Browse open tasks** from TaskMarket's public REST API (no wallet needed).
- **Fetch full task details** including descriptions, rewards, and expiry.
- **List submissions** for any public task.
- **Check wallet address and USDC balance** via the first-party CLI.
- **Claim** a claim-mode task, **submit work**, **submit benchmark proofs**,
  or **create** a new task -- always gated behind an explicit `approve=true`
  parameter (no silent spending).

The CLI (`@lucid-agents/taskmarket`) owns the wallet, EIP-191 signatures, and
X402 payments. This server never handles private keys.

## Tools

| Tool | Mode | Description |
|------|------|-------------|
| `taskmarket_list_open_tasks` | read | Browse open tasks (limit, tags filter) |
| `taskmarket_get_task` | read | Get full task details by ID |
| `taskmarket_list_submissions` | read | List submissions for a task |
| `taskmarket_wallet_address` | read | Print the configured wallet address |
| `taskmarket_wallet_balance` | read | Print USDC balance |
| `taskmarket_claim_task` | write | Claim a claim-mode task (approve=true) |
| `taskmarket_submit_work` | write | Submit work/artifact to a task (approve=true) |
| `taskmarket_proof` | write | Submit a benchmark proof (approve=true, 0.001 USDC) |
| `taskmarket_create_task` | write | Create a new escrowed task (approve=true) |

## Setup

### 1. Install the TaskMarket CLI

```bash
npm install -g @lucid-agents/taskmarket@latest
```

Fix the bin symlink if `taskmarket address` reports "command not found":

```bash
ln -sf ../lib/node_modules/@lucid-agents/taskmarket/dist/index.js ~/.npm-global/bin/taskmarket
```

### 2. Initialise your wallet (one-time)

```bash
taskmarket init
taskmarket legal accept
taskmarket deposit
```

Fund the wallet with Base Mainnet USDC.

### 3. Run the MCP server

In one terminal:

```bash
python server.py
# Server starts on http://localhost:8000/sse
```

### 4. Run the example agent

```bash
cd examples/mcp/mcp_taskmarket
uv run main.py
```

## Safety design

- All write tools require `approve=true`. Without it, the tool returns an
  approval-required message instead of performing the action.
- The server never stores or accepts private keys, seed phrases, or tokens.
- Wallet identity and X402 payment flows are handled entirely by the CLI.
- Read tools use the public REST API with no wallet required.

## Files

- `server.py` -- the MCP SSE server with all TaskMarket tools.
- `main.py` -- example `mcp-agent` client that browses tasks and checks wallet.
- `mcp_agent.config.yaml` -- mcp-agent configuration referencing the server.
- `requirements.txt` -- Python dependencies.
