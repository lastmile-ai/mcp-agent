import hashlib
import hmac
import json
import time
from typing import Optional
import httpx


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
