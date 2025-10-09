from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_agent.context.runtime import run_assembling_phase, MemoryArtifactStore, MemorySSEEmitter
from mcp_agent.context.models import AssembleInputs, AssembleOptions
from mcp_agent.context.filelengths import FileLengthProvider


async def assemble_before_prompt(
    run_id: str,
    inputs: AssembleInputs,
    repo: Optional[str] = None,
    commit_sha: Optional[str] = None,
    code_version: Optional[str] = None,
    tool_versions: Optional[Dict[str, str]] = None,
    artifact_store=None,
    sse=None,
) -> Dict[str, Any]:
    """
    Drop-in helper for engines. Calls the assembling phase then returns a dict:
    {
      "manifest": Manifest,
      "pack_hash": str,
      "report": AssembleReport,
      "artifact_id": str,
    }
    The engine can call this before building the prompt.
    """
    store = artifact_store or MemoryArtifactStore()
    emitter = sse or MemorySSEEmitter()

    # Derive file lengths for clamp when possible
    flp = FileLengthProvider()
    uris = list(set((inputs.changed_paths or []) + (inputs.referenced_files or [])))
    lengths = flp.lengths_for(uris)

    opts = AssembleOptions(neighbor_radius=20)  # retain defaults
    # Attach optional attribute recognized by assemble()
    setattr(opts, "file_lengths", lengths)

    manifest, pack_hash, report = await run_assembling_phase(
        run_id=run_id,
        inputs=inputs,
        opts=opts,
        artifact_store=store,
        sse=emitter,
        code_version=code_version,
        tool_versions=tool_versions,
        repo=repo,
        commit_sha=commit_sha,
    )

    return {
        "manifest": manifest,
        "pack_hash": pack_hash,
        "report": report,
        "artifact_id": f"mem://{run_id}/artifacts/context/manifest.json",
    }
