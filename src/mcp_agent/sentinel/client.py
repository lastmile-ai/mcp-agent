import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

import httpx
from opentelemetry import metrics

class SentinelClient:
    """
    Asynchronous client for Sentinel API communication.
    
    This client uses httpx.AsyncClient for scalable, non-blocking HTTP requests
    to the MCP-agent Sentinel service for registration and authorization.
    
    All API calls are async and must be awaited.
    """

    def __init__(self, base_url: str, signing_key: str, http: Optional[httpx.AsyncClient] = None):
        """
        Initialize the Sentinel client with async HTTP support.
        
        Args:
            base_url: Base URL of the Sentinel service
            signing_key: Secret key for HMAC request signing
            http: Optional pre-configured AsyncClient (defaults to new AsyncClient with 3s timeout)
        """
        self.base_url = base_url.rstrip("/")
        self.signing_key = signing_key.encode("utf-8")
        # Use AsyncClient for non-blocking HTTP operations
        self.http = http or httpx.AsyncClient(timeout=3.0)

    def _sign(self, payload: dict) -> str:
        """
        Generate HMAC-SHA256 signature for request payload.
        
        This is a synchronous helper method used by async API methods.
        
        Args:
            payload: Dictionary to sign
            
        Returns:
            Hex-encoded HMAC signature
        """
        msg = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hmac.new(self.signing_key, msg, hashlib.sha256).hexdigest()

    async def register(self, agent_id: str, version: str) -> None:
        """
        Register an agent with the Sentinel service (async).
        
        This async method performs agent registration and must be awaited.
        
        Args:
            agent_id: Unique identifier for the agent
            version: Version string of the agent
            
        Raises:
            httpx.HTTPStatusError: If registration fails
        """
        payload = {"agent_id": agent_id, "version": version, "ts": int(time.time())}
        sig = self._sign(payload)
        # Async HTTP POST request - must be awaited
        r = await self.http.post(
            f"{self.base_url}/v1/agents/register",
            json=payload,
            headers={"X-Signature": sig}
        )
        r.raise_for_status()

    async def authorize(self, project_id: str, run_type: str) -> bool:
        """
        Check authorization for a project run (async).
        
        This async method queries authorization status and must be awaited.
        
        Args:
            project_id: Project identifier to authorize
            run_type: Type of run being authorized
            
        Returns:
            True if authorized, False otherwise
            
        Raises:
            httpx.HTTPStatusError: If request fails (except 403)
        """
        payload = {"project_id": project_id, "run_type": run_type}
        sig = self._sign(payload)
        # Async HTTP POST request - must be awaited
        r = await self.http.post(
            f"{self.base_url}/v1/authorize",
            json=payload,
            headers={"X-Signature": sig}
        )
        if r.status_code == 200:
            data = r.json()
            return bool(data.get("allow", False))
        if r.status_code == 403:
            return False
        r.raise_for_status()
        return False

    async def close(self) -> None:
        """
        Close the underlying AsyncClient connection (async).
        
        Should be called when done with the client to clean up resources.
        Must be awaited.
        """
        await self.http.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes HTTP client."""
        await self.close()

# === PR-05A: GitHub token issuing via Sentinel (consumer) ===
# OTel counter for observability
_meter = metrics.get_meter(__name__)
try:
    _sentinel_token_counter = _meter.create_counter("sentinel_token_requests_total")
except Exception:  # defensive: older OTel APIs
    _sentinel_token_counter = None

class _ResponseLike:
    """Minimal shim for typing clarity."""
    def __init__(self, r: httpx.Response): self.r = r
    def json(self) -> Dict[str, Any]: return self.r.json()
    def raise_for_status(self): return self.r.raise_for_status()

async def issue_github_token(
    repo: str,
    permissions: dict | None = None,
    ttl_seconds: int | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    Issue a short-lived GitHub token from Sentinel.
    Reads SENTINEL_URL and SENTINEL_HMAC_KEY from environment.
    Optional guard: GITHUB_ALLOWED_REPO must match if set.
    """
    base_url = os.getenv("SENTINEL_URL")
    signing_key = os.getenv("SENTINEL_HMAC_KEY")
    if not base_url or not signing_key:
        raise RuntimeError("SENTINEL_URL and SENTINEL_HMAC_KEY are required")

    allowed = os.getenv("GITHUB_ALLOWED_REPO")
    if allowed and allowed != repo:
        raise ValueError("Repo not allowed by GITHUB_ALLOWED_REPO")

    payload: Dict[str, Any] = {"repo": repo}
    if permissions:
        payload["permissions"] = permissions
    if ttl_seconds:
        payload["ttl_seconds"] = ttl_seconds
    if trace_id:
        payload["trace_id"] = trace_id

    # Sign with same HMAC pattern as register/authorize
    client = SentinelClient(base_url=base_url, signing_key=signing_key)
    try:
        sig = client._sign(payload)  # reuse internal signer
        r = await client.http.post(
            f"{client.base_url}/v1/github/token",
            json=payload,
            headers={"X-Signature": sig},
        )
        r.raise_for_status()
        data = r.json()
        # no token bytes in logs; record only outcome
        try:
            if _sentinel_token_counter:
                _sentinel_token_counter.add(1, {"outcome": "ok"})
        except Exception:
            pass
        # Expected {token, expires_at, granted_permissions}
        return data
    except Exception:
        try:
            if _sentinel_token_counter:
                _sentinel_token_counter.add(1, {"outcome": "error"})
        except Exception:
            pass
        raise
    finally:
        await client.close()

# Optional: method on SentinelClient for direct usage
async def _client_issue_github_token(self, repo: str, permissions: dict | None = None, ttl_seconds: int | None = None, trace_id: str | None = None) -> dict:
    return await issue_github_token(repo=repo, permissions=permissions, ttl_seconds=ttl_seconds, trace_id=trace_id)

# Bind method if class exists
try:
    setattr(SentinelClient, "issue_github_token", _client_issue_github_token)
except Exception:
    pass
