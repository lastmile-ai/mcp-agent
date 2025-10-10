"""Discovery and normalization for the tools registry."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import string
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import httpx
import yaml

from mcp_agent.logging.logger import get_logger

from .models import ToolItem, ToolProbeResult, ToolSource, ToolsResponse


logger = get_logger(__name__)


def _sanitize(value: str) -> str:
    allowed = string.printable
    return "".join(ch for ch in value if ch in allowed).strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- OpenTelemetry metrics -------------------------------------------------


class _NoopHistogram:
    def record(self, *_args, **_kwargs) -> None:  # pragma: no cover - noop
        return None


class _NoopCounter:
    def add(self, *_args, **_kwargs) -> None:  # pragma: no cover - noop
        return None


class _NoopGauge:
    def set(self, *_args, **_kwargs) -> None:  # pragma: no cover - noop
        return None


class _AsyncGauge:
    def __init__(self, name: str, unit: str, description: str):
        try:  # pragma: no cover - optional dependency
            from opentelemetry import metrics
            from opentelemetry.metrics import Observation

            self._value = 0
            self._attributes: Mapping[str, str] | None = None
            meter = metrics.get_meter("mcp_agent.registry")

            def _callback(_options):
                yield Observation(self._value, attributes=self._attributes or {})

            meter.create_observable_gauge(
                name,
                unit=unit,
                description=description,
                callbacks=[_callback],
            )
        except Exception:  # pragma: no cover - instrumentation optional
            self._value = 0
            self._attributes = None

    def set(self, value: int, attributes: Mapping[str, str] | None = None) -> None:
        self._value = value
        if attributes is not None:
            self._attributes = attributes


try:  # pragma: no cover - optional dependency
    from opentelemetry import metrics

    _meter = metrics.get_meter("mcp_agent.registry")
    _discovery_latency = _meter.create_histogram(
        "tools_discovery_latency_ms",
        unit="ms",
        description="Latency of MCP tool discovery probes",
    )
    _capabilities_counter = _meter.create_counter(
        "tools_capabilities_total",
        unit="1",
        description="Count of capabilities discovered per tool",
    )
    _registry_size_gauge = _AsyncGauge(
        "tools_registry_size",
        unit="1",
        description="Number of tools tracked in the registry",
    )
    _alive_gauge = _AsyncGauge(
        "tools_alive_total",
        unit="1",
        description="Number of tools currently marked alive",
    )
    _discovery_failures = _meter.create_counter(
        "tools_discovery_failures_total",
        unit="1",
        description="Number of discovery failures",
    )
except Exception:  # pragma: no cover - instrumentation optional
    _discovery_latency = _NoopHistogram()
    _capabilities_counter = _NoopCounter()
    _registry_size_gauge = _AsyncGauge("noop", unit="1", description="noop")
    _alive_gauge = _AsyncGauge("noop_alive", unit="1", description="noop")
    _discovery_failures = _NoopCounter()


@dataclass
class LoaderConfig:
    tools_yaml_path: str = os.getenv("TOOLS_YAML_PATH", "tools/tools.yaml")
    discovery_timeout_ms: int = int(os.getenv("DISCOVERY_TIMEOUT_MS", "1500"))
    discovery_user_agent: str = os.getenv("DISCOVERY_UA", "agent-mcp/PR-06")
    allowed_hosts: Sequence[str] | None = tuple(
        host.strip()
        for host in os.getenv("REGISTRY_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )


def _load_yaml(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def _normalize_inventory(raw: Any) -> list[ToolSource]:
    if isinstance(raw, Mapping):
        candidates: Iterable[Any] = raw.get("tools") or raw.get("servers") or raw.values()
    elif isinstance(raw, Sequence):
        candidates = raw
    else:
        raise ValueError("tools inventory must be a list or mapping")

    sources: list[ToolSource] = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        tool_id = str(item.get("id") or "").strip()
        base_url = str(item.get("base_url") or "").strip()
        name = str(item.get("name") or tool_id or base_url).strip()
        if not tool_id or not base_url:
            logger.warning(
                "tools.registry.invalid_entry",
                tool_id=tool_id or "<missing>",
                base_url=base_url or "<missing>",
            )
            continue
        headers = {
            str(k): str(v)
            for k, v in (item.get("headers") or {}).items()
            if isinstance(k, str) and isinstance(v, (str, int, float))
        }
        tags = [str(tag) for tag in (item.get("tags") or []) if isinstance(tag, (str, int))]
        sources.append(
            ToolSource(
                id=tool_id,
                name=name or tool_id,
                base_url=base_url,
                headers=headers,
                tags=sorted(set(tags)),
            )
        )

    sources.sort(key=lambda entry: (entry.name.lower(), entry.id))
    return sources


def load_inventory(config: LoaderConfig) -> list[ToolSource]:
    raw = _load_yaml(config.tools_yaml_path)
    return _normalize_inventory(raw)


def _parse_capabilities(data: Any) -> list[str]:
    if isinstance(data, Mapping):
        collected: set[str] = set()
        for key, value in data.items():
            if isinstance(value, Mapping):
                collected.add(str(key))
                collected.update(str(k) for k in value.keys())
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                for item in value:
                    collected.add(str(item))
            else:
                collected.add(str(key))
        return sorted(collected)
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        return sorted({str(item) for item in data})
    if isinstance(data, str):
        return [data]
    return []


def _is_health_ok(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        status = payload.get("status") or payload.get("state") or payload.get("ok")
        if isinstance(status, str):
            return status.lower() in {"ok", "pass", "healthy"}
        if isinstance(status, bool):
            return status
    if isinstance(payload, bool):
        return payload
    return False


class DiscoveryError(Exception):
    """Raised when discovery fails for a tool."""


class ToolRegistryLoader:
    """Loader responsible for discovering tool metadata."""

    def __init__(self, config: LoaderConfig | None = None):
        self.config = config or LoaderConfig()

    def load_sources(self) -> list[ToolSource]:
        logger.debug("tools.registry.load", phase="load", path=self.config.tools_yaml_path)
        return load_inventory(self.config)

    def _build_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(self.config.discovery_timeout_ms / 1000.0)
        headers = {"User-Agent": self.config.discovery_user_agent}
        return httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False)

    def _check_host(self, base_url: str) -> None:
        if not self.config.allowed_hosts:
            return
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        if host not in self.config.allowed_hosts:
            raise DiscoveryError(f"host_not_allowed:{host}")
        if parsed.scheme not in {"http", "https"}:
            raise DiscoveryError("invalid_scheme")

    async def probe(self, source: ToolSource) -> ToolProbeResult:
        await asyncio.sleep(0)  # allow cancellation before network I/O
        started = time.perf_counter()
        timestamp = _now()
        failure_reason: str | None = None
        name = _sanitize(source.name) or source.id
        version = "0.0.0"
        capabilities: list[str] = []
        alive = False

        try:
            self._check_host(source.base_url)
        except DiscoveryError as exc:
            failure_reason = str(exc)
            latency_ms = (time.perf_counter() - started) * 1000.0
            _discovery_latency.record(latency_ms, {"tool_id": source.id, "result": "fail"})
            _discovery_failures.add(1, {"tool_id": source.id, "reason": failure_reason})
            return ToolProbeResult(
                id=source.id,
                name=name,
                version=version,
                base_url=source.base_url,
                alive=False,
                latency_ms=latency_ms,
                capabilities=[],
                tags=source.tags,
                timestamp=timestamp,
                failure_reason=failure_reason,
            )

        async with self._build_client() as client:
            headers = {**client.headers, **source.headers}
            well_known_url = f"{source.base_url.rstrip('/')}/.well-known/mcp"
            health_url = f"{source.base_url.rstrip('/')}/health"
            try:
                response = await client.get(well_known_url, headers=headers)
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, Mapping):
                        if payload.get("name"):
                            name = _sanitize(str(payload.get("name"))) or name
                        if payload.get("version"):
                            version = _sanitize(str(payload.get("version"))) or version
                        capabilities = _parse_capabilities(payload.get("capabilities"))
                else:
                    failure_reason = f"well_known_status:{response.status_code}"
            except Exception as exc:  # pragma: no cover - httpx edge cases
                failure_reason = f"well_known_error:{exc.__class__.__name__}"

            try:
                health_response = await client.get(health_url, headers=headers)
                if health_response.status_code == 200:
                    alive = _is_health_ok(health_response.json()) or True
                else:
                    alive = False
                    failure_reason = failure_reason or f"health_status:{health_response.status_code}"
            except Exception as exc:  # pragma: no cover - httpx edge cases
                alive = False
                failure_reason = failure_reason or f"health_error:{exc.__class__.__name__}"

        latency_ms = (time.perf_counter() - started) * 1000.0
        result_label = "ok" if failure_reason is None and capabilities else "fail"
        _discovery_latency.record(latency_ms, {"tool_id": source.id, "result": result_label})
        if result_label == "ok":
            for capability in capabilities:
                _capabilities_counter.add(1, {"tool_id": source.id, "capability": capability})
        else:
            _discovery_failures.add(1, {"tool_id": source.id, "reason": failure_reason or "unknown"})

        return ToolProbeResult(
            id=source.id,
            name=name or source.name,
            version=version or "0.0.0",
            base_url=source.base_url,
            alive=bool(alive),
            latency_ms=latency_ms,
            capabilities=capabilities,
            tags=source.tags,
            timestamp=timestamp,
            failure_reason=failure_reason,
        )


def compute_registry_hash(items: Sequence[ToolItem]) -> str:
    payload = json.dumps(
        [item.model_dump(mode="json") for item in items],
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    encoded = base64.b64encode(digest).decode("ascii")
    return f"sha256-{encoded}"


def build_response(items: Sequence[ToolItem]) -> ToolsResponse:
    generated_at = _now()
    registry_hash = compute_registry_hash(items)
    return ToolsResponse(registry_hash=registry_hash, generated_at=generated_at, items=list(items))


def update_registry_metrics(items: Sequence[ToolItem]) -> None:
    try:
        _registry_size_gauge.set(len(items))
        _alive_gauge.set(sum(1 for item in items if item.alive))
    except Exception:  # pragma: no cover - metrics optional
        pass

