
import asyncio
import os
import pytest

from mcp_agent.config import Settings, MCPServerSettings, MCPSettings
from mcp_agent.mcp.mcp_server_registry import ServerRegistry

@pytest.mark.asyncio
async def test_pre_init_hook_injects_env_and_headers(monkeypatch):
    os.environ["SENTINEL_URL"] = "https://sentinel.internal"
    os.environ["SENTINEL_HMAC_KEY"] = "k"
    os.environ["GITHUB_ALLOWED_REPO"] = "owner/name"

    # Settings with two servers
    servers = {
        "github": MCPServerSettings(
            name="github",
            transport="stdio",
            command="server-github",
            env={},
        ),
        "rest": MCPServerSettings(
            name="rest",
            transport="http",
            url="https://api.example",
            headers={},
            command="n/a"
        ),
    }
    cfg = Settings(mcp=MCPSettings(servers=servers))

    reg = ServerRegistry(config=cfg)

    # Register hook just like app does
    from mcp_agent.sentinel.client import issue_github_token
    async def fake_issue(repo: str, **kw):
        return {"token":"ghs_X","expires_at":"2099-01-01T00:00:00Z","granted_permissions":{}}
    monkeypatch.setattr("mcp_agent.sentinel.client.issue_github_token", fake_issue, raising=True)

    async def gh_hook(server_name, config, context):
        data = await issue_github_token(repo="owner/name")
        token = data["token"]
        env = dict(getattr(config, "env", {}) or {})
        env["GITHUB_TOKEN"] = token
        env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
        config.env = env
        headers = dict(getattr(config, "headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        config.headers = headers

    reg.register_pre_init_hook("github", gh_hook)

    # Execute for stdio server 'github'
    await reg.execute_pre_init_hook("github", servers["github"], context=None)
    assert servers["github"].env.get("GITHUB_TOKEN") == "ghs_X"
    assert servers["github"].env.get("GITHUB_PERSONAL_ACCESS_TOKEN") == "ghs_X"

    # For 'rest', simulate fallback via command containing server-github
    servers["rest"].command = "server-github via-http"
    await reg.execute_pre_init_hook("rest", servers["rest"], context=None)
    assert servers["rest"].headers.get("Authorization") == "Bearer ghs_X"
