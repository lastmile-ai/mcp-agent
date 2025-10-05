import os
from typing import Optional
from mcp_agent.logging.logger import get_logger
from mcp_agent.config import Settings, MCPServerSettings
import httpx, hmac, hashlib, json

logger = get_logger(__name__)

def _is_github_server(config: MCPServerSettings) -> bool:
    cmd = (config.command or "") + " " + " ".join(config.args or [])
    cmd = cmd.lower()
    return (config.name or "").lower() == "github" or "server-github" in cmd or "mcp-server-github" in cmd

def register_github_preinit(registry, settings: Settings) -> None:
    """Register a pre-init hook that injects a short-lived GitHub token from Sentinel."""
    async def preinit(server_name: str, config: MCPServerSettings, context: Optional[object] = None) -> None:
        if not _is_github_server(config):
            return
        base_url = os.getenv("SENTINEL_URL") or (getattr(settings, "sentinel", None) and getattr(settings.sentinel, "base_url", None))
        hmac_key = os.getenv("SENTINEL_HMAC_KEY") or (getattr(settings, "sentinel", None) and getattr(settings.sentinel, "hmac_key", None))
        if not base_url or not hmac_key:
            logger.warning("Sentinel config missing; skipping GitHub token injection")
            return
        repo = os.getenv("GITHUB_ALLOWED_REPO") or ((config.env or {}).get("GITHUB_ALLOWED_REPO") if config.env else None)
        if not repo:
            logger.info("GITHUB_ALLOWED_REPO not set; skipping token injection")
            return
        try:
            async with httpx.AsyncClient(timeout=3.0) as http:
                payload = {"repo": repo}
                msg = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
                sig = hmac.new(hmac_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
                headers = {"X-Sentinel-Signature": f"sha256={sig}", "Content-Type": "application/json"}
                url = base_url.rstrip("/") + "/v1/github/token"
                r = await http.post(url, headers=headers, content=json.dumps(payload))
                r.raise_for_status()
                resp = r.json()
                token = resp.get("token")
                if not token:
                    raise RuntimeError("No token returned from Sentinel")
                # mutate env in-memory
                env = dict(config.env or {})
                env["GITHUB_TOKEN"] = token
                env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
                # Hide helper guard key
                env.pop("GITHUB_ALLOWED_REPO", None)
                config.env = env
                # For HTTP/SSE/WebSocket transports, set Authorization bearer header
                if getattr(config, 'transport', 'stdio') != 'stdio':
                    headers = dict(getattr(config, 'headers', None) or {})
                    headers['Authorization'] = f"Bearer {token}"
                    config.headers = headers
            logger.info(f"Injected short-lived GitHub token for server '{server_name}' and repo '{repo}'")
        except Exception as e:
            logger.exception("Failed to inject GitHub token from Sentinel: %s", e)
            raise
    # Register under name 'github'; hook itself guards by command/args too
    registry.register_pre_init_hook("github", preinit)
