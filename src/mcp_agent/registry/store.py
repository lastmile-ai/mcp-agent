import asyncio
import os
import time
from typing import Any, Dict, List, Optional

_DEFAULT_TTL = int(os.getenv("REGISTRY_REFRESH_SEC", "300"))

class ToolRegistryStore:
    def __init__(self, tools_yaml_path: Optional[str] = None, ttl_sec: Optional[int] = None):
        self._tools_yaml_path = tools_yaml_path
        self._ttl = _DEFAULT_TTL if ttl_sec is None else ttl_sec
        self._registry: List[Dict[str, Any]] = []
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()

    def _is_stale(self) -> bool:
        return (time.time() - self._last_refresh) > self._ttl or not self._registry

    async def refresh(self) -> List[Dict[str, Any]]:
        # Import here to avoid circular dependency
        from .loader import load_tools_yaml, discover
        
        async with self._lock:
            entries = load_tools_yaml(self._tools_yaml_path)
            self._registry = await discover(entries)
            self._last_refresh = time.time()
            return list(self._registry)

    async def get_all(self) -> List[Dict[str, Any]]:
        if self._is_stale():
            await self.refresh()
        return list(self._registry)

# module-level singleton for convenience
store = ToolRegistryStore()
