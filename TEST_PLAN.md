# MCP Agent Env & Secrets Workflow Test Plan

This plan exercises the end-to-end experience introduced in this branch from a
developer’s perspective, covering authoring, deployment, CLI management, and
runtime validation. It assumes you have the latest CLI installed via `uvx
mcp-agent` and access to MCP Agent Cloud.

## Prerequisites

- Working directory contains a sample project (e.g., `uvx mcp-agent init`).
- Authenticated CLI: `uvx mcp-agent login` succeeded or `MCP_API_KEY` set.
- Cloud app exists (or can be created) for the project.

---

## 1. Author env declarations

1. Open `mcp_agent.config.yaml`.
2. Add an `env` list with mixed syntax:
   ```yaml
   env:
     - OPENAI_API_KEY              # no fallback, must come from env
     - {SUPABASE_URL: "https://db.example.com"}  # fallback literal
   ```
3. Ensure `OPENAI_API_KEY` is set in your shell; leave `SUPABASE_URL`
   unset to exercise the fallback prompt later.
4. Validate schema support by running `uvx mcp-agent build --dry-run` (or
   letting your editor’s YAML validation pass).

Expected: No schema errors, config lints cleanly.

---

## 2. Deploy and capture env secrets

1. Run `uvx mcp-agent deploy <app-name> --non-interactive` in the project
   directory.
2. Observe prompts/logs:
   - Deployment should read `OPENAI_API_KEY` from the environment.
   - For `SUPABASE_URL`, deployment should auto-use the fallback literal.
3. After success, inspect generated files:
   - `mcp_agent.deployed.secrets.yaml` contains:
     ```yaml
     env:
       - OPENAI_API_KEY: mcpac_sc_...
       - SUPABASE_URL: mcpac_sc_...
     ```
   - `mcp_agent.deployed.config.yaml` matches the resolved config but has no
     raw secret values (search for `sk-` or `SUPABASE_URL` literal; only env
     placeholder should remain).

Expected: Deployment succeeds; both deployed files exist; config snapshot
contains no plaintext secrets.

---

## 3. Verify runtime env injection

1. Tail logs via `uvx mcp-agent cloud logger tail <app-name> --since 5m`.
2. Push a request to the server (e.g., via the MCP client or sample workflow)
   that prints/uses the environment variables.

Expected: App has access to `OPENAI_API_KEY` and `SUPABASE_URL` via `os.environ`
without checking in secrets locally.

---

## 4. Exercise `cloud secrets` commands

### 4.1 List
`uvx mcp-agent cloud secrets list <app-name>`

Expected: Table shows both env keys with masked handles.

### 4.2 Add
`uvx mcp-agent cloud secrets add EXTRA_TOKEN super-secret <app-name>`
`uvx mcp-agent cloud secrets add --from-env-file .env.local --app <app-name>`

Expected: Command prints “Created secret for EXTRA_TOKEN …”.

Optional: add an OAuth/authorization block to `mcp_agent.config.yaml` and redeploy to ensure `mcp_agent.deployed.config.yaml` captures those AnyHttpUrl fields without error.

### 4.3 Pull
`uvx mcp-agent cloud secrets pull <app-name> --format env`

Expected:
- `.env.mcp-cloud` is created (or updated when `--force` is provided) with `KEY=value` pairs, quoted when necessary.
- Running `uvx mcp-agent ...` commands afterward automatically picks up `.env.mcp-cloud` (after any local `.env`) with no manual sourcing.
- Re-run with `--format yaml --output pulled.yaml` to confirm the YAML path still works when needed.

### 4.4 Remove & redeploy
1. `uvx mcp-agent cloud secrets remove EXTRA_TOKEN <app-name>`
2. Confirm `list` no longer shows `EXTRA_TOKEN`.
3. Run `uvx mcp-agent deploy <app-name> --non-interactive` again.

Expected: Deploy succeeds even though the previous handle was deleted (CLI
provisions a new handle automatically). `mcp_agent.deployed.secrets.yaml`
contains whichever env keys remain.

---

## 5. Semantics of fallbacks/prompts

1. Unset `SUPABASE_URL` and remove the fallback from `mcp_agent.config.yaml`.
2. Run `uvx mcp-agent deploy <app-name>` (interactive mode).

Expected: CLI prompts “Enter value for environment variable 'SUPABASE_URL'…”.
Entering a value stores it as a secret; redeploying should reuse the handle.
3. Modify `.env.mcp-cloud`, re-run a local command (e.g., `uvx mcp-agent build --dry-run`), and confirm the new value is picked up without editing `mcp_agent.secrets.yaml`, proving the `.env` loading order works (`.env` > `.env.mcp-cloud` > config fallbacks).

---

## 6. Bundle integrity

1. Inspect the deployment bundle (optional) to confirm it contains:
   - `mcp_agent.deployed.config.yaml`
   - `mcp_agent.deployed.secrets.yaml` (handles)
   - *Not* `mcp_agent.secrets.yaml`
2. Confirm `.mcpacignore` or custom ignore files behave as documented.

---

## 7. Regression checks

1. Run the targeted test suite locally:
   `uv run pytest tests/cli/cloud/test_materialize.py tests/config/test_env_settings.py`
2. Spot-check docs:
   - `docs/cloud/deployment-quickstart.mdx`
   - `docs/cloud/mcp-agent-cloud/manage-secrets.mdx`
   - `docs/reference/cli.mdx`
3. Validate schema:
   `cat schema/mcp-agent.config.schema.json | rg '"env"'` (ensure description
   matches documentation).

---

## 8. Cleanup

1. Remove generated files if not committing:
   `rm mcp_agent.deployed.config.yaml mcp_agent.deployed.secrets.yaml`
2. Delete temporary secrets via `cloud secrets remove` as needed.
3. Optionally terminate the deployment: `uvx mcp-agent cloud servers terminate
   <app-id>`.

---

Following this plan walks through every end-user-facing change:

- Authoring env specs in config (schema + docs)
- Deploy-time materialization of config & secrets
- CLI secret management (list/add/remove/pull)
- Handling of deleted handles across redeploys
- Runtime behavior (env injection)

Use it as a smoke/regression checklist before shipping.***
