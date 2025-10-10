"""In-memory helper for managing Sentinel issued GitHub tokens."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mcp_agent.sentinel import client as sentinel_client


@dataclass
class CachedToken:
    token: str
    expires_at: float
    metadata: Dict[str, Any]

    @property
    def remaining_ttl(self) -> float:
        return self.expires_at - time.time()


class TokenManager:
    """Keeps the most recently issued GitHub token in memory."""

    def __init__(self, repo: str) -> None:
        self._repo = repo
        self._lock = asyncio.Lock()
        self._cached: CachedToken | None = None

    async def ensure_valid(
        self,
        *,
        min_required_ttl_s: float,
        permissions: Optional[Dict[str, Any]] = None,
        trace_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> CachedToken:
        async with self._lock:
            if self._cached and self._cached.remaining_ttl > min_required_ttl_s:
                return self._cached
            ttl = ttl_seconds or int(min_required_ttl_s * 2) or 600
            response = await sentinel_client.issue_github_token(
                repo=self._repo,
                permissions=permissions,
                ttl_seconds=ttl,
                trace_id=trace_id,
            )
            token = response.get("token")
            expires_at = response.get("expires_at")
            if token is None or expires_at is None:
                raise RuntimeError("Sentinel response missing token fields")
            cached = CachedToken(
                token=token,
                expires_at=float(expires_at),
                metadata={k: v for k, v in response.items() if k not in {"token"}},
            )
            self._cached = cached
            return cached

    def reset(self) -> None:
        self._cached = None


__all__ = ["TokenManager", "CachedToken"]
