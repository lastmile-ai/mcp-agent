from __future__ import annotations
import json
from typing import Any, Dict, Optional, Protocol, Tuple
from .assemble import assemble_context, ToolKit, must_include_missing
from .errors import BudgetError
from .toolkit import AggregatorToolKit
from .models import AssembleInputs, AssembleOptions, AssembleReport, Manifest
from .settings import ContextSettings
from .logutil import redact_event, redact_path

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
    tk = toolkit or AggregatorToolKit(trace_id=trace_id, repo_sha=commit_sha)
    store = artifact_store or MemoryArtifactStore()
    sse_emitter = sse or MemorySSEEmitter()

    start_evt = {"phase": "ASSEMBLING", "status": "start", "run_id": run_id, "repo": repo, "commit_sha": commit_sha}
    await sse_emitter.emit(run_id, redact_event(start_evt, cfg.REDACT_PATH_GLOBS))

    tool_versions_map = tool_versions
    if tool_versions_map is None and isinstance(tk, AggregatorToolKit):
        tool_versions_map = await tk.tool_versions()

    try:
        manifest, pack_hash, report = await assemble_context(
            inputs=inputs,
            opts=opts,
            toolkit=tk,
            code_version=code_version,
            tool_versions=tool_versions_map,
            telemetry_attrs={"run_id": run_id or "", "repo": repo or "", "commit_sha": commit_sha or "", "trace_id": trace_id or ""},
        )
    except BudgetError as exc:
        violation_evt = {
            "phase": "ASSEMBLING",
            "status": "violation",
            "violation": True,
            "overflow": list(exc.overflow),
        }
        await sse_emitter.emit(run_id, redact_event(violation_evt, cfg.REDACT_PATH_GLOBS))
        raise

    manifest_bytes = json.dumps(json.loads(manifest.model_dump_json()), indent=2).encode("utf-8")
    art_id = await store.put(run_id, "artifacts/context/manifest.json", manifest_bytes, content_type="application/json")

    example_uri = ""
    if manifest.slices:
        candidate = manifest.slices[0].uri
        example_uri = candidate if redact_path(candidate, cfg.REDACT_PATH_GLOBS) == candidate else ""

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
        "example_uri": example_uri,
    }
    await sse_emitter.emit(run_id, redact_event(end_evt, cfg.REDACT_PATH_GLOBS))

    if report.violation:
        violation_evt = {
            "phase": "ASSEMBLING",
            "status": "violation",
            "violation": True,
            "overflow": [dict(item) for item in report.overflow],
        }
        await sse_emitter.emit(run_id, redact_event(violation_evt, cfg.REDACT_PATH_GLOBS))

    if cfg.ENFORCE_NON_DROPPABLE:
        missing = must_include_missing(inputs, manifest)
        if missing:
            # Signal violation and raise to fail the run
            await sse_emitter.emit(run_id, {"phase": "ASSEMBLING", "status": "violation", "violation": True, "non_droppable_missing": missing})
            raise RuntimeError("non_droppable_missing")

    return manifest, pack_hash, report
