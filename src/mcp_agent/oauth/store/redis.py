from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

from ..records import TokenRecord
from .base import TokenStore, TokenStoreKey


class RedisTokenStore(TokenStore):
    """Redis-backed token store for multi-instance deployments."""

    def __init__(
        self,
        *,
        url: str,
        prefix: str = "mcp_agent:oauth_tokens",
    ) -> None:
        try:
            import redis.asyncio as redis  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "RedisTokenStore requires the 'redis' optional dependency. "
                "Install with `pip install mcp-agent[redis]`."
            ) from exc

        if not url:
            raise ValueError(
                "Redis token store requires a redis_url configuration value"
            )

        self._client = redis.from_url(url, decode_responses=True)
        self._prefix = prefix.rstrip(":")
        self._lock = asyncio.Lock()

    def _make_key(self, key: TokenStoreKey) -> str:
        parts = [
            self._prefix,
            quote(key.user_key, safe=""),
            quote(key.resource or "", safe=""),
            quote(key.authorization_server or "", safe=""),
            quote(key.scope_fingerprint or "", safe=""),
        ]
        return ":".join(parts)

    async def get(self, key: TokenStoreKey) -> TokenRecord | None:
        redis_key = self._make_key(key)
        payload = await self._client.get(redis_key)
        if not payload:
            return None
        data = json.loads(payload)
        return TokenRecord.model_validate(data)

    async def set(self, key: TokenStoreKey, record: TokenRecord) -> None:
        async with self._lock:
            redis_key = self._make_key(key)
            await self._client.set(redis_key, json.dumps(record.model_dump()))

    async def delete(self, key: TokenStoreKey) -> None:
        redis_key = self._make_key(key)
        await self._client.delete(redis_key)

    async def aclose(self) -> None:
        await self._client.close()
