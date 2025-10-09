from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .models import Span
from .settings import ContextSettings

try:
    from mcp_agent.registry.store import store as registry_store  # type: ignore
except Exception:  # pragma: no cover
    registry_store = None  # type: ignore

try:
    from mcp_agent.client.http import HTTPClient  # type: ignore
except Exception:  # pragma: no cover
    HTTPClient = None  # type: ignore


def _hash_params(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class MemoCache:
    def __init__(self, max_items: int = 512):
        self.max = max_items
        self.data: Dict[Tuple[str, str, str], Any] = {}
        self.order: List[Tuple[str, str, str]] = []

    def get(self, key: Tuple[str, str, str]) -> Optional[Any]:
        return self.data.get(key)

    def put(self, key: Tuple[str, str, str], value: Any) -> None:
        if key in self.data:
            return
        self.data[key] = value
        self.order.append(key)
        if len(self.order) > self.max:
            oldest = self.order.pop(0)
            self.data.pop(oldest, None)


class RegistryToolKit:
    """
    Registry-backed ToolKit using shared HTTPClient.
    - HMAC signing on each request via X-Signature (same as Sentinel)
    - Memoization keyed by (op, repo_sha|tool_versions, params_hash)
    - Optional transport injection for tests
    """
    def __init__(self, repo_sha: Optional[str] = None, trace_id: Optional[str] = None, transport=None, tool_versions: Optional[Dict[str,str]] = None):
        self.repo_sha = repo_sha or ""
        self.trace_id = trace_id or ""
        self.tool_versions = tool_versions or {}
        self.settings = ContextSettings()
        self.cache = MemoCache()
        self._tools: Dict[str, Dict[str, Any]] = {}
        self.transport = transport
        # HMAC key from env to reuse Sentinel scheme
        self._hmac_key = os.getenv("MCP_CONTEXT_HMAC_KEY") or os.getenv("SENTINEL_SIGNING_KEY") or ""
        try:
            self._refresh_registry()
        except Exception:
            pass

    async def _to_thread(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    def _refresh_registry(self):
        if registry_store is None:
            self._tools = {}
            return
        import asyncio
        tools = asyncio.get_event_loop().run_until_complete(registry_store.get_all())  # type: ignore
        self._tools = {}
        for t in tools or []:
            name = str(t.get("name") or t.get("tool") or t.get("id") or "")
            base_url = str(t.get("base_url") or t.get("url") or "")
            caps = set((t.get("capabilities") or []))
            self._tools[name] = {"base_url": base_url, "caps": caps}

    def _pick(self, capability: str) -> Optional[Tuple[str, str]]:
        for name, meta in self._tools.items():
            if capability in meta.get("caps", set()):
                return name, meta["base_url"]
        # Fallback: assume a synthetic single tool if provided via env
        single = os.getenv("MCP_CONTEXT_SINGLE_TOOL_BASE")
        if single:
            return "tool", single
        return None

    def _client(self, tool: str, base_url: str):
        if HTTPClient is None:
            raise RuntimeError("HTTPClient unavailable")
        return HTTPClient(tool=tool, base_url=base_url, transport=self.transport)

    def _sign(self, payload: Dict[str, Any]) -> Optional[str]:
        if not self._hmac_key:
            return None
        msg = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hmac.new(self._hmac_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    async def _post_json(self, client, path: str, payload: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        headers = {}
        sig = self._sign(payload)
        if sig:
            headers["X-Signature"] = sig
            headers["Authorization"] = f"Signature {sig}"
        kwargs = {"headers": headers}
        if timeout_ms:
            kwargs["timeout"] = timeout_ms / 1000.0
        return await self._to_thread(client.post_json, path, json=payload, **kwargs)

    def _cache_key(self, op: str, payload: Dict[str, Any]) -> Tuple[str, str, str]:
        v = "|".join([f"{k}:{self.tool_versions.get(k,'')}" for k in sorted(self.tool_versions)])
        return op, f"{self.repo_sha}|{v}", _hash_params(payload)

    # Public capabilities

    async def semantic_search(self, query: str, top_k: int) -> List[Span]:
        pick = self._pick("semantic_search")
        if not pick:
            return []
        tool, base = pick
        payload = {"query": query, "top_k": int(top_k), "trace_id": self.trace_id, "repo_sha": self.repo_sha}
        key = self._cache_key("semantic_search", payload)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        client = self._client(tool, base)
        data = await self._post_json(client, "/semantic_search", payload, self.settings.SEMANTIC_TIMEOUT_MS)
        res = [Span(**s) for s in data.get("spans", [])]
        self.cache.put(key, res)
        return res

    async def symbols(self, target: str) -> List[Span]:
        pick = self._pick("symbols")
        if not pick:
            return []
        tool, base = pick
        payload = {"target": target, "trace_id": self.trace_id, "repo_sha": self.repo_sha}
        key = self._cache_key("symbols", payload)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        client = self._client(tool, base)
        data = await self._post_json(client, "/symbols", payload, self.settings.SYMBOLS_TIMEOUT_MS)
        res = [Span(**s) for s in data.get("spans", [])]
        self.cache.put(key, res)
        return res

    async def neighbors(self, uri: str, line_or_start: int, radius: int) -> List[Span]:
        pick = self._pick("neighbors")
        if not pick:
            return []
        tool, base = pick
        payload = {"uri": uri, "line_or_start": int(line_or_start), "radius": int(radius), "trace_id": self.trace_id, "repo_sha": self.repo_sha}
        key = self._cache_key("neighbors", payload)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        client = self._client(tool, base)
        data = await self._post_json(client, "/neighbors", payload, self.settings.NEIGHBORS_TIMEOUT_MS)
        res = [Span(**s) for s in data.get("spans", [])]
        self.cache.put(key, res)
        return res

    async def patterns(self, globs: List[str]) -> List[Span]:
        pick = self._pick("patterns")
        if not pick:
            return []
        tool, base = pick
        payload = {"globs": list(globs or []), "trace_id": self.trace_id, "repo_sha": self.repo_sha}
        key = self._cache_key("patterns", payload)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        client = self._client(tool, base)
        data = await self._post_json(client, "/patterns", payload, self.settings.PATTERNS_TIMEOUT_MS)
        res = [Span(**s) for s in data.get("spans", [])]
        self.cache.put(key, res)
        return res
