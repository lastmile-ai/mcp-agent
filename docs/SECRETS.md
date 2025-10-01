# Secrets Bridge (GitHub + Vendors)

Ephemeral credentials only. Start with GitHub; vendors can follow the same pattern.

## Config
- `GITHUB_APP_ID`
- `GITHUB_PRIVATE_KEY` (PEM)
- Optional: `GITHUB_API` (default `https://api.github.com`)

## Usage
```python
from mcp_agent.secrets.bridge import mount_github_token_for_run

async with mount_github_token_for_run(
    target="github-mcp-server",
    installation_id=123456,
    permissions={"contents":"read","pull_requests":"write"},
    repositories=["repo-1"],
    ttl_seconds=900,
) as tok:
    headers = tok.as_header()  # {'Authorization': 'token …'}
    # pass headers only to github-mcp-server client
```

## Telemetry
- `secret_issuance_total{kind="github-installation"}`
- `secret_revocation_total{kind="github-installation"}`

## Redaction
Add `mcp_agent.middleware.redact.RedactionMiddleware` to the ASGI stack to avoid logging secrets.
