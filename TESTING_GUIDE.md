# OAuth Flow Validation Guide

This checklist lets you flip between the original `feat/mcp_agent_oauth` branch and the current branch, exercise every scenario we discussed, and confirm the token flows (including caching) behave as intended. All commands use `uv` for Python execution.

---

## 0. One-Time Setup

### 0.1 Create a Virtual Environment

```bash
uv venv
source .venv/bin/activate
```

### 0.2 Install Project (with optional extras)

```bash
uv pip install -e .[oauth,cli,redis]
```

### 0.3 Start Temporal (required by the workflow examples)

```bash
temporal server start-dev
```

### 0.4 Set Secrets You'll Reuse

```bash
export GITHUB_CLIENT_ID=your_client_id
export GITHUB_CLIENT_SECRET=your_client_secret
  export GITHUB_ACCESS_TOKEN=ghp_your_pat   # for token bootstrap flows
```

### 0.5 (Optional) Start Redis for Redis-backed tests

```bash
docker run --rm -p 6379:6379 redis:7-alpine
export OAUTH_REDIS_URL=redis://127.0.0.1:6379
```

---

## 1. Original Branch (`feat/mcp_agent_oauth`)

```bash
git checkout feat/mcp_agent_oauth
```

### 1.1 Unit Tests

```bash
uv run python -m pytest tests/test_oauth_utils.py tests/test_audience_validation.py
# add tests/test_token_manager.py if it exists in that branch
```

### 1.2 Examples

#### 1.2.1 Preconfigured (static token cache)

- Terminal 1:
  ```bash
  uv run python examples/oauth/preconfigured/main.py
  ```

#### 1.2.2 Workflow Pre-Authorize

- Terminal 1:
  ```bash
  uv run python examples/oauth/pre_authorize/worker.py
  ```
- Terminal 2:
  ```bash
  uv run python examples/oauth/pre_authorize/main.py
  ```
- Terminal 3:
  ```bash
  uv run python examples/oauth/pre_authorize/client.py
  ```
  Optional: rerun the client with `--skip-store-credentials` to confirm cached token reuse.

#### 1.2.3 Dynamic Interactive Flow

- Terminal 1:
  ```bash
  uv run python examples/oauth/dynamic_auth/worker.py
  ```
- Terminal 2:
  ```bash
  uv run python examples/oauth/dynamic_auth/main.py
  ```
- Terminal 3:
  ```bash
  uv run python examples/oauth/dynamic_auth/client.py
  ```

#### 1.2.4 Standalone OAuth Helper

```bash
uv run python examples/oauth/preconfigured/oauth_demo.py
```

---

## 2. Current Branch (`your current working branch`)

```bash
git checkout <current-branch>
```

### 2.1 Unit Tests

```bash
uv run python -m pytest tests/test_oauth_utils.py tests/test_audience_validation.py tests/test_token_manager.py
```

_(Fix pytest/pytest_asyncio integration if you still have the autoload error before running.)_

### 2.2 Examples

#### 2.2.1 Interactive Tool Flow (dynamic auth)

- Terminal 1:
  ```bash
  uv run python examples/oauth/interactive_tool/server.py
  ```
- Terminal 2:
  ```bash
  uv run python examples/oauth/interactive_tool/client.py
  ```
  After finishing the first run, run the client **again** (with the server still running). The second invocation should return immediately with no additional auth prompt—confirming token caching.

#### 2.2.1b Client-only loopback (basic agent)

- In `examples/basic/oauth_basic_agent/`, copy the secrets template and add your credentials:
  ```bash
  cd examples/basic/oauth_basic_agent
  cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml  # fill in keys/client details
  uv pip install -r requirements.txt
  export GITHUB_CLIENT_ID=your_client_id   # skip if secrets file already has these
  export GITHUB_CLIENT_SECRET=your_client_secret
  uv run python main.py
  ```
  On first run the browser opens to GitHub; authorize and the agent completes. Run the same command again and it should reuse the cached token without prompting. To choose different loopback ports, set `oauth.loopback_ports` in `mcp_agent.config.yaml`.

#### 2.2.2 Workflow Pre-Authorize

- Terminal 1:
  ```bash
  uv run python examples/oauth/pre_authorize/worker.py
  ```
- Terminal 2:
  ```bash
  uv run python examples/oauth/pre_authorize/main.py
  ```
- Terminal 3:
  ```bash
  uv run python examples/oauth/pre_authorize/client.py
  ```
  Repeat with `--skip-store-credentials` to verify cached token reuse after the workflow has been seeded once.

#### 2.2.3 Redis-backed Token Cache (optional)

- Make sure Redis is running (step 0.5 above).
- With `OAUTH_REDIS_URL` exported and the redis extra installed, re-run either example. Tokens will persist across server restarts, so you can stop and restart the server and rerun the client to confirm the Redis cache is used.

---

## 3. Manual Validation Matrix

| Scenario                             | Terminal(s)                               | Expected outcome                                                            |
| ------------------------------------ | ----------------------------------------- | --------------------------------------------------------------------------- |
| Workflow pre-authorize (both branches) | Worker + server + client                | First run seeds token, subsequent run with `--skip-store-credentials` reuses it. |
| Interactive flow (both branches)     | Server + client                           | First run asks for auth; immediate re-run uses cached token without prompt. |
| Redis token caching (current branch) | Same as above but with Redis env vars set | Tokens survive server restart thanks to Redis-backed store.                 |

---

Following this checklist will let you validate the complete OAuth functionality on both branches, including the multiple-user token caching behavior.
