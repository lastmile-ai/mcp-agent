# PR-15B — GitHub Repo Bootstrap (agent-mcp)

This PR lives in **agent-mcp**. It seeds minimal CI and CODEOWNERS via github-mcp-server.
Sentinel only mints short-lived tokens (PR-05B).

## Layout
- templates/repo/ci/node.yml
- templates/repo/ci/python.yml
- templates/repo/CODEOWNERS
- src/mcp_agent/services/github_mcp_client.py
- src/mcp_agent/tasks/bootstrap_repo.py
- src/mcp_agent/api/routes/bootstrap_repo.py  (wired under /v1 if imported from public router)
- tests/bootstrap/test_plan_and_guard.py

## API
`POST /v1/bootstrap/repo`
```json
{ "owner":"org", "repo":"name", "trace_id":"uuid", "language":"auto|node|python", "dry_run":false }
```

## Security
Agent calls `github-mcp-server` over HTTP(S). That server uses Sentinel-issued short-lived tokens.
No long-lived tokens stored here.
