from __future__ import annotations
import json
from typing import Any, Dict, Optional, Protocol, Tuple
from .assemble import assemble_context, ToolKit, NoopToolKit
from .models import AssembleInputs, AssembleOptions, AssembleReport, Manifest
from .settings import ContextSettings
from .logutil import redact_event

class ArtifactStore(Protocol):
    async def put(self, run_id: str, path: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    # Returns an artifact id or path.

class SSEEmitter(Protocol):
    async def emit(self, run_id: str, event: Dict[str, Any]) -> None: ...
    # Sends a server-sent event to stream clients.

class MemoryArtifactStore:
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
    def __init__(self) -> None:
        self.events: Dict[str, list[Dict[str, Any]]] = {}

    async def emit(self, run_id: str, event: Dict[str, Any]) -> None:
        self.events.setdefault(run_id, []).append(event)

def _must_include_covered(inputs: AssembleInputs, manifest: Manifest):
    missing = []
    for ms in inputs.must_include or []:
        ok = False
        for sl in manifest.slices:
            if sl.uri == ms.uri and int(sl.start) <= int(ms.start) and int(sl.end) >= int(ms.end):
                ok = True
                break
        if not ok:
            missing.append({"uri": ms.uri, "start": int(ms.start), "end": int(ms.end), "reason": ms.reason or ""})
    return missing

async def run_assembling_phase(
    run_id: str,
    inputs: AssembleInputs,
    opts: Optional[AssembleOptions] = None,
    toolkit: Optional[ToolKit] = None,
    artifact_store: Optional[ArtifactStore] = None,
    sse: Optional[SSEEmitter] = None,
    code_version: Optional[str] = None,
    tool_versions: Optional[Dict[str, str]] = None,
    repo: Optional[str] = None,
    commit_sha: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Tuple[Manifest, str, AssembleReport]:
    """
    Executes the ContextPack assembly stage within the run loop.
    Emits redacted SSE events and persists artifacts/context/manifest.json.
    Enforces non-droppable coverage when ENFORCE_NON_DROPPABLE=true.
    """
    cfg = ContextSettings()
    tk = toolkit or NoopToolKit()
    store = artifact_store or MemoryArtifactStore()
    sse_emitter = sse or MemorySSEEmitter()

    start_evt = {"phase": "ASSEMBLING", "status": "start", "run_id": run_id, "repo": repo, "commit_sha": commit_sha}
    await sse_emitter.emit(run_id, redact_event(start_evt, cfg.REDACT_PATH_GLOBS))

    manifest, pack_hash, report = await assemble_context(
        inputs=inputs,
        opts=opts,
        toolkit=tk,
        code_version=code_version,
        tool_versions=tool_versions,
        telemetry_attrs={"run_id": run_id or "", "repo": repo or "", "commit_sha": commit_sha or "", "trace_id": trace_id or ""},
    )

    manifest_bytes = json.dumps(json.loads(manifest.model_dump_json()), indent=2).encode("utf-8")
    art_id = await store.put(run_id, "artifacts/context/manifest.json", manifest_bytes, content_type="application/json")

    end_evt = {
        "phase": "ASSEMBLING",
        "status": "end",
        "pack_hash": pack_hash,
        "run_id": run_id,
        "repo": repo,
        "commit_sha": commit_sha,
        "files_out": report.files_out,
        "tokens_out": report.tokens_out,
        "artifact": art_id,
    }
    await sse_emitter.emit(run_id, redact_event(end_evt, cfg.REDACT_PATH_GLOBS))

    if cfg.ENFORCE_NON_DROPPABLE:
        missing = _must_include_covered(inputs, manifest)
        if missing:
            # Signal violation and raise to fail the run
            await sse_emitter.emit(run_id, {"phase": "ASSEMBLING", "status": "violation", "violation": True, "non_droppable_missing": missing})
            raise RuntimeError("non_droppable_missing")

    return manifest, pack_hash, report
