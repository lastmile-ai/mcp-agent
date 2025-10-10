from __future__ import annotations

import asyncio
import json
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    ReadResourceResult,
    TextContent,
    Tool,
)

from mcp_agent.context.models import Span
from mcp_agent.context.settings import ContextSettings
from mcp_agent.core.context import Context, get_current_context
from mcp_agent.mcp.mcp_aggregator import MCPAggregator, SEP


def _canonical_hash(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _schema_version(schema: Dict[str, Any] | None) -> str:
    if not schema:
        return ""
    for key in ("version", "$id", "$schema"):
        value = schema.get(key)
        if isinstance(value, str) and value:
            return value
    return _canonical_hash(schema)


def _normalize_capability(name: str) -> str:
    return name.replace("-", "_").lower()


@dataclass(frozen=True)
class _ToolRecord:
    fqn: str
    aggregator_name: str
    server_name: str
    local_name: str
    schema_version: str
    tool: Tool


class AggregatorToolKit:
    """Adapter that exposes ContextPack tool capabilities via an MCPAggregator."""

    CAPABILITY_ALIASES: Dict[str, Tuple[str, ...]] = {
        "semantic_search": ("semantic_search", "semantic-search"),
        "symbols": ("symbols", "symbol_lookup", "symbols_lookup"),
        "neighbors": ("neighbors", "neighbor_lines", "neighbor-context"),
        "patterns": ("patterns", "pattern_search", "pattern-search"),
    }

    def __init__(
        self,
        *,
        trace_id: Optional[str] = None,
        repo_sha: Optional[str] = None,
        tool_versions: Optional[Dict[str, str]] = None,
        context: Optional[Context] = None,
        aggregator: Optional[MCPAggregator] = None,
    ) -> None:
        self.trace_id = trace_id or ""
        self.repo_sha = repo_sha or ""
        self._explicit_tool_versions = tool_versions or {}
        self._context = context
        self._settings = ContextSettings()

        self._aggregator: Optional[MCPAggregator] = aggregator
        self._aggregator_lock = asyncio.Lock()

        self._tool_records: Dict[str, _ToolRecord] | None = None
        self._tool_order: List[str] = []
        self._capability_index: Dict[str, List[_ToolRecord]] = {}
        self._server_names: List[str] = []
        self._tool_index_lock = asyncio.Lock()

    async def list_tools(self) -> List[Tool]:
        await self._ensure_tool_index()
        return [
            self._tool_records[fqn].tool.model_copy(update={"name": fqn})
            for fqn in self._tool_order
        ]

    async def list_prompts(self, server_name: Optional[str] = None) -> ListPromptsResult:
        agg = await self._ensure_aggregator()
        if server_name:
            normalized = self._normalize_server_filter(server_name)
            res = await agg.list_prompts(server_name=normalized)
        else:
            res = await agg.list_prompts()
        prompts = [
            prompt.model_copy(update={"name": self._namespaced_to_fqn(prompt.name)})
            for prompt in res.prompts or []
        ]
        return ListPromptsResult(prompts=prompts, nextCursor=getattr(res, "nextCursor", None))

    async def get_prompt(
        self,
        name: str,
        arguments: Optional[Dict[str, str]] = None,
    ) -> GetPromptResult:
        agg = await self._ensure_aggregator()
        namespaced = self._fqn_to_namespaced(name)
        server, _ = self._split_fqn(name)
        result = await agg.get_prompt(name=namespaced, arguments=arguments)
        if hasattr(result, "namespaced_name"):
            result.namespaced_name = name  # type: ignore[attr-defined]
        if hasattr(result, "server_name"):
            result.server_name = server  # type: ignore[attr-defined]
        if hasattr(result, "prompt_name"):
            result.prompt_name = name.split(".", 1)[-1]  # type: ignore[attr-defined]
        return result

    async def list_resources(self, server_name: Optional[str] = None) -> ListResourcesResult:
        agg = await self._ensure_aggregator()
        if server_name:
            normalized = self._normalize_server_filter(server_name)
            res = await agg.list_resources(server_name=normalized)
        else:
            res = await agg.list_resources()
        resources = [
            resource.model_copy(update={"name": self._namespaced_to_fqn(resource.name)})
            for resource in res.resources or []
        ]
        return ListResourcesResult(
            resources=resources,
            nextCursor=getattr(res, "nextCursor", None),
        )

    async def read_resource(self, uri: str) -> ReadResourceResult:
        agg = await self._ensure_aggregator()
        namespaced = self._fqn_to_namespaced(uri)
        return await agg.read_resource(uri=namespaced)

    async def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> CallToolResult:
        agg = await self._ensure_aggregator()
        namespaced = self._fqn_to_namespaced(name)
        return await agg.call_tool(name=namespaced, arguments=arguments)

    async def tool_versions(self) -> Dict[str, str]:
        if self._explicit_tool_versions:
            return dict(self._explicit_tool_versions)
        await self._ensure_tool_index()
        return {fqn: self._tool_records[fqn].schema_version for fqn in self._tool_order}

    async def semantic_search(self, query: str, top_k: int) -> List[Span]:
        payload = {
            "query": query,
            "top_k": int(top_k),
            "trace_id": self.trace_id,
            "repo_sha": self.repo_sha,
        }
        return await self._call_span_tool("semantic_search", payload)

    async def symbols(self, target: str) -> List[Span]:
        payload = {
            "target": target,
            "trace_id": self.trace_id,
            "repo_sha": self.repo_sha,
        }
        return await self._call_span_tool("symbols", payload)

    async def neighbors(
        self, uri: str, line_or_start: int, radius: int
    ) -> List[Span]:
        payload = {
            "uri": uri,
            "line_or_start": int(line_or_start),
            "radius": int(radius),
            "trace_id": self.trace_id,
            "repo_sha": self.repo_sha,
        }
        return await self._call_span_tool("neighbors", payload)

    async def patterns(self, globs: Iterable[str]) -> List[Span]:
        payload = {
            "globs": list(globs or []),
            "trace_id": self.trace_id,
            "repo_sha": self.repo_sha,
        }
        return await self._call_span_tool("patterns", payload)

    async def _call_span_tool(
        self, capability: str, arguments: Dict[str, Any]
    ) -> List[Span]:
        record = await self._select_capability(capability)
        if record is None:
            return []
        timeout_ms = {
            "semantic_search": self._settings.SEMANTIC_TIMEOUT_MS,
            "symbols": self._settings.SYMBOLS_TIMEOUT_MS,
            "neighbors": self._settings.NEIGHBORS_TIMEOUT_MS,
            "patterns": self._settings.PATTERNS_TIMEOUT_MS,
        }.get(capability, 0)
        if timeout_ms:
            timeout = max(0.001, timeout_ms / 1000.0)
        else:
            timeout = None

        async def _invoke() -> CallToolResult:
            return await self.call_tool(record.fqn, arguments)

        try:
            if timeout is not None:
                result = await asyncio.wait_for(_invoke(), timeout=timeout)
            else:
                result = await _invoke()
        except Exception:
            return []

        data = self._extract_payload(result)
        spans_payload = []
        if isinstance(data, dict):
            spans_payload = data.get("spans") or []
        elif isinstance(data, list):
            spans_payload = data

        spans: List[Span] = []
        for item in spans_payload:
            if not isinstance(item, dict):
                continue
            span = Span(**item)
            span.tool = record.fqn
            spans.append(span)
        return spans

    def _extract_payload(self, result: CallToolResult) -> Any:
        if result.structuredContent is not None:
            return result.structuredContent
        for content in result.content or []:
            if isinstance(content, TextContent):
                try:
                    return json.loads(content.text or "null")
                except json.JSONDecodeError:
                    continue
        return None

    async def _select_capability(self, capability: str) -> Optional[_ToolRecord]:
        await self._ensure_tool_index()
        aliases = self.CAPABILITY_ALIASES.get(capability, (capability,))
        for alias in aliases:
            normalized = _normalize_capability(alias)
            candidates = self._capability_index.get(normalized)
            if candidates:
                return candidates[0]
        normalized_capability = _normalize_capability(capability)
        candidates = self._capability_index.get(normalized_capability)
        return candidates[0] if candidates else None

    async def _ensure_tool_index(self) -> None:
        if self._tool_records is not None:
            return
        async with self._tool_index_lock:
            if self._tool_records is not None:
                return
            agg = await self._ensure_aggregator()
            try:
                server_names = await agg.list_servers()
            except AttributeError:
                server_names = getattr(agg, "server_names", [])
            self._server_names = sorted(server_names)
            server_set = set(self._server_names)

            tool_records: Dict[str, _ToolRecord] = {}
            order: List[str] = []
            capability_map: Dict[str, List[_ToolRecord]] = {}

            for server in self._server_names:
                tools_result: ListToolsResult = await agg.list_tools(server_name=server)
                for tool in tools_result.tools or []:
                    namespaced = tool.name
                    if namespaced.startswith(f"{server}{SEP}"):
                        local_name = namespaced[len(server) + 1 :]
                    else:
                        local_name = self._strip_server_prefix(namespaced, server_set)
                    fqn = f"{server}.{local_name}"
                    record = _ToolRecord(
                        fqn=fqn,
                        aggregator_name=namespaced,
                        server_name=server,
                        local_name=local_name,
                        schema_version=_schema_version(tool.inputSchema),
                        tool=tool,
                    )
                    tool_records[fqn] = record
                    order.append(fqn)
                    normalized = _normalize_capability(local_name)
                    capability_map.setdefault(normalized, []).append(record)

            order.sort()
            for candidates in capability_map.values():
                candidates.sort(key=lambda rec: rec.fqn)

            self._tool_records = tool_records
            self._tool_order = order
            self._capability_index = capability_map

    async def _ensure_aggregator(self) -> MCPAggregator:
        if self._aggregator is not None:
            return self._aggregator
        async with self._aggregator_lock:
            if self._aggregator is not None:
                return self._aggregator
            context = self._context or get_current_context()
            server_registry = getattr(context, "server_registry", None)
            if server_registry is None:
                server_names: List[str] = []
            else:
                server_names = sorted(server_registry.registry.keys())  # type: ignore[attr-defined]
            aggregator = MCPAggregator(server_names=server_names, context=context)
            await aggregator.initialize()
            self._aggregator = aggregator
            return aggregator

    def _normalize_server_filter(self, server_name: str) -> str:
        if "." in server_name:
            return server_name.split(".", 1)[0]
        return server_name

    def _fqn_to_namespaced(self, fqn: str) -> str:
        server, remainder = self._split_fqn(fqn)
        if not remainder:
            return server
        return f"{server}{SEP}{remainder.replace('.', SEP)}"

    def _namespaced_to_fqn(self, namespaced: str) -> str:
        server, local = self._parse_namespaced(namespaced)
        if not local:
            return server
        return f"{server}.{local}"

    def _parse_namespaced(self, namespaced: str) -> Tuple[str, str]:
        if not self._server_names:
            return self._split_simple(namespaced)
        parts = namespaced.split(SEP)
        server_candidates = set(self._server_names)
        for idx in range(len(parts), 0, -1):
            prefix = SEP.join(parts[:idx])
            if prefix in server_candidates:
                remainder = SEP.join(parts[idx:])
                return prefix, remainder
        return self._split_simple(namespaced)

    def _split_simple(self, value: str) -> Tuple[str, str]:
        if SEP not in value:
            return value, ""
        head, tail = value.split(SEP, 1)
        return head, tail

    def _strip_server_prefix(self, namespaced: str, server_set: set[str]) -> str:
        prefix, remainder = self._parse_namespaced(namespaced)
        if prefix in server_set:
            return remainder
        return remainder or namespaced

    def _split_fqn(self, fqn: str) -> Tuple[str, str]:
        if "." not in fqn:
            return fqn, ""
        return fqn.split(".", 1)


class NoopToolKit:
    async def semantic_search(self, query: str, top_k: int) -> List[Span]:
        return []

    async def symbols(self, target: str) -> List[Span]:
        return []

    async def neighbors(self, uri: str, line_or_start: int, radius: int) -> List[Span]:
        return []

    async def patterns(self, globs: Iterable[str]) -> List[Span]:
        return []
