from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional, Protocol, Tuple

from .assemble import assemble_context, ToolKit, NoopToolKit
from .models import AssembleInputs, AssembleOptions, AssembleReport, Manifest
from .telemetry import meter


class ArtifactStore(Protocol):
    async def put(self, run_id: str, path: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    # Returns an artifact id or path.


class SSEEmitter(Protocol):
    async def emit(self, run_id: str, event: Dict[str, Any]) -> None: ...
    # Sends a server-sent event to stream clients.


class MemoryArtifactStore:
    """Simple in-memory artifact store for tests or local runs."""
    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], bytes] = {}
        self._ct: Dict[Tuple[str, str], str] = {}

    async def put(self, run_id: str, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        key = (run_id, path)
        self._data[key] = data
        self._ct[key] = content_type
        return f"mem://{run_id}/{path}"

    def get(self, run_id: str, path: str) -> bytes:
        return self._data[(run_id, path)]

    def content_type(self, run_id: str, path: str) -> str:
        return self._ct[(run_id, path)]


class MemorySSEEmitter:
    """Collects events for assertions in tests."""
    def __init__(self) -> None:
        self.events: Dict[str, list[Dict[str, Any]]] = {}

    async def emit(self, run_id: str, event: Dict[str, Any]) -> None:
        self.events.setdefault(run_id, []).append(event)


async def run_assembling_phase(
    run_id: str,
    inputs: AssembleInputs,
    opts: Optional[AssembleOptions] = None,
    toolkit: Optional[ToolKit] = None,
    artifact_store: Optional[ArtifactStore] = None,
    sse: Optional[SSEEmitter] = None,
    code_version: Optional[str] = None,
    tool_versions: Optional[Dict[str, str]] = None,
) -> Tuple[Manifest, str, AssembleReport]:
    """
    Executes the ContextPack assembly stage within the run loop.
    - Emits SSE {"phase":"ASSEMBLING", ...}
    - Persists artifacts/context/manifest.json
    - Returns (manifest, pack_hash, report)
    """
    m = meter()
    t0 = time.perf_counter()

    tk = toolkit or NoopToolKit()
    store = artifact_store or MemoryArtifactStore()
    sse_emitter = sse or MemorySSEEmitter()

    # Announce start of assembling
    await sse_emitter.emit(run_id, {"phase": "ASSEMBLING", "status": "start"})

    manifest, pack_hash, report = await assemble_context(
        inputs=inputs,
        opts=opts,
        toolkit=tk,
        code_version=code_version,
        tool_versions=tool_versions,
    )

    # Persist manifest.json as an artifact
    manifest_bytes = json.dumps(json.loads(manifest.model_dump_json()), indent=2).encode("utf-8")
    art_id = await store.put(run_id, "artifacts/context/manifest.json", manifest_bytes, content_type="application/json")

    # Announce completion with hash and quick stats
    await sse_emitter.emit(
        run_id,
        {
            "phase": "ASSEMBLING",
            "status": "end",
            "pack_hash": pack_hash,
            "files_out": report.files_out,
            "tokens_out": report.tokens_out,
            "artifact": art_id,
        },
    )

    dur_ms = (time.perf_counter() - t0) * 1000.0
    m.record_duration_ms(dur_ms, {"phase": "assemble", "stage": "runloop"})

    return manifest, pack_hash, report
