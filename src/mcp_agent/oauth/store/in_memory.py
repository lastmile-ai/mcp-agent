"""In-memory token store for local development and testing."""

from __future__ import annotations

import asyncio
from typing import Dict

from .base import TokenStore, TokenStoreKey
from ..records import TokenRecord


class InMemoryTokenStore(TokenStore):
    def __init__(self) -> None:
        self._records: Dict[TokenStoreKey, TokenRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: TokenStoreKey) -> TokenRecord | None:
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                return None
            return record

    async def set(self, key: TokenStoreKey, record: TokenRecord) -> None:
        async with self._lock:
            self._records[key] = record

    async def delete(self, key: TokenStoreKey) -> None:
        async with self._lock:
            self._records.pop(key, None)
