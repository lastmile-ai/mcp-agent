"""In-memory snapshot store for the tools registry."""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from mcp_agent.logging.logger import get_logger

from .loader import (
    ToolRegistryLoader,
    build_response,
    update_registry_metrics,
)
from .models import ToolItem, ToolProbeResult, ToolSource, ToolsResponse


logger = get_logger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ToolState:
    source: ToolSource
    item: ToolItem
    last_success: datetime | None = None
    last_capabilities: list[str] = field(default_factory=list)
    last_version: str = "0.0.0"
    last_name: str = ""
    consecutive_failures: int = 0
    next_refresh_at: datetime = field(default_factory=_now)
    failure_reason: str | None = None
    ever_succeeded: bool = False


class ToolRegistryError(RuntimeError):
    """Base class for registry availability errors."""


class ToolRegistryUnavailable(ToolRegistryError):
    """Raised when no snapshot is available yet."""


class ToolRegistryMisconfigured(ToolRegistryError):
    """Raised when configuration prevents discovery."""


class ToolRegistryStore:
    """Maintains a cached snapshot of discovered tools."""

    def __init__(
        self,
        loader: ToolRegistryLoader | None = None,
        *,
        refresh_interval_sec: int | None = None,
        stale_max_sec: int | None = None,
        enabled: bool | None = None,
    ):
        self._loader = loader or ToolRegistryLoader()
        self._refresh_interval = refresh_interval_sec or _env_int("REGISTRY_REFRESH_SEC", 60)
        self._stale_max = stale_max_sec or _env_int("REGISTRY_STALE_MAX_SEC", 3600)
        self._enabled = (
            _env_bool("TOOLS_REGISTRY_ENABLED", True)
            if enabled is None
            else enabled
        )
        self._states: dict[str, ToolState] = {}
        self._snapshot: ToolsResponse | None = None
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._misconfigured: Exception | None = None
        self._ever_succeeded = False

    async def start(self) -> None:
        if not self._enabled:
            logger.info("tools.registry.disabled", phase="lifecycle")
            return
        if self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._run_refresh_loop())

    async def stop(self) -> None:
        if self._refresh_task is None:
            return
        self._stop_event.set()
        self._refresh_task.cancel()
        try:
            await self._refresh_task
        except asyncio.CancelledError:  # pragma: no cover - lifecycle cleanup
            pass
        finally:
            self._refresh_task = None

    async def _run_refresh_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self.refresh()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.error(
                        "tools.registry.refresh_failed",
                        phase="refresh",
                        error=str(exc),
                    )
                wait = self._refresh_interval
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                except asyncio.TimeoutError:
                    continue
        finally:
            self._stop_event.clear()

    async def ensure_started(self) -> None:
        if self._enabled and self._refresh_task is None:
            await self.start()

    async def refresh(self, force: bool = False) -> ToolsResponse:
        async with self._lock:
            sources = await self._load_sources()
            due_states = self._select_states_to_probe(sources, force=force)
            if due_states:
                for state in due_states:
                    result = await self._loader.probe(state.source)
                    self._update_state_from_probe(state, result)
            self._prune_missing_sources({source.id for source in sources})
            snapshot = self._build_snapshot()
            self._snapshot = snapshot
            update_registry_metrics(snapshot.items)
            return snapshot

    async def _load_sources(self) -> list[ToolSource]:
        try:
            sources = self._loader.load_sources()
            self._misconfigured = None
            return sources
        except FileNotFoundError as exc:
            self._misconfigured = exc
            logger.error(
                "tools.registry.missing_inventory",
                phase="load",
                error=str(exc),
            )
            return []
        except Exception as exc:  # pragma: no cover - defensive
            self._misconfigured = exc
            logger.error(
                "tools.registry.load_failed",
                phase="load",
                error=str(exc),
            )
            return []

    def _select_states_to_probe(
        self, sources: Iterable[ToolSource], *, force: bool
    ) -> list[ToolState]:
        states: list[ToolState] = []
        now = _now()
        seen_ids = set()
        for source in sources:
            seen_ids.add(source.id)
            state = self._states.get(source.id)
            if state is None:
                item = ToolItem(
                    id=source.id,
                    name=source.name,
                    version="0.0.0",
                    base_url=source.base_url,
                    alive=False,
                    latency_ms=0.0,
                    capabilities=[],
                    tags=source.tags,
                    last_checked_ts=now,
                    failure_reason="pending",
                    consecutive_failures=0,
                )
                state = ToolState(
                    source=source,
                    item=item,
                    next_refresh_at=now,
                    last_name=source.name,
                )
                self._states[source.id] = state
            else:
                state.source = source

            if force or state.next_refresh_at <= now:
                states.append(state)

        states.sort(key=lambda entry: (entry.source.name.lower(), entry.source.id))
        return states

    def _prune_missing_sources(self, available_ids: Iterable[str]) -> None:
        for tool_id in list(self._states.keys()):
            if tool_id not in available_ids:
                logger.warning(
                    "tools.registry.removed",
                    phase="normalize",
                    tool_id=tool_id,
                )
                self._states.pop(tool_id, None)

    def _update_state_from_probe(self, state: ToolState, probe: ToolProbeResult) -> None:
        timestamp = probe.timestamp
        failure_reason = probe.failure_reason
        success = failure_reason is None and bool(probe.capabilities)

        if success:
            state.consecutive_failures = 0
            state.last_success = timestamp
            state.last_capabilities = list(probe.capabilities)
            state.last_version = probe.version
            state.last_name = probe.name
            state.failure_reason = None
            state.ever_succeeded = True
            self._ever_succeeded = True
        else:
            state.consecutive_failures += 1
            state.failure_reason = failure_reason or "unknown"

        capabilities: list[str]
        last_success = state.last_success
        if success:
            capabilities = probe.capabilities
        elif last_success is not None and timestamp - last_success <= timedelta(seconds=self._stale_max):
            capabilities = list(state.last_capabilities)
        else:
            capabilities = []

        version = probe.version if success else (state.last_version or "0.0.0")
        name = probe.name if success else (state.last_name or state.source.name)
        alive = probe.alive if success else False

        state.item = ToolItem(
            id=state.source.id,
            name=name,
            version=version,
            base_url=state.source.base_url,
            alive=alive,
            latency_ms=probe.latency_ms,
            capabilities=capabilities,
            tags=state.source.tags,
            last_checked_ts=timestamp,
            failure_reason=state.failure_reason,
            consecutive_failures=state.consecutive_failures,
        )

        multiplier = 1.0 + random.uniform(-0.1, 0.1)
        interval = self._refresh_interval * multiplier
        if state.consecutive_failures:
            backoff = min(2 ** state.consecutive_failures, 10)
            interval = min(self._refresh_interval * backoff, self._refresh_interval * 10)
            interval *= multiplier
        state.next_refresh_at = timestamp + timedelta(seconds=interval)

    def _build_snapshot(self) -> ToolsResponse:
        items = [state.item for state in self._states.values()]
        items.sort(key=lambda item: (item.name.lower(), item.id))
        snapshot = build_response(items)
        logger.info(
            "tools.registry.snapshot",
            phase="normalize",
            count=len(items),
            registry_hash=snapshot.registry_hash,
        )
        return snapshot

    async def get_snapshot(self) -> ToolsResponse:
        if self._snapshot is None:
            await self.refresh(force=True)
        if self._snapshot is None:
            if self._misconfigured is not None:
                raise ToolRegistryMisconfigured(str(self._misconfigured))
            raise ToolRegistryUnavailable("registry snapshot unavailable")
        return self._snapshot

    @property
    def ever_succeeded(self) -> bool:
        return self._ever_succeeded

    @property
    def misconfigured(self) -> Exception | None:
        return self._misconfigured


store = ToolRegistryStore()

