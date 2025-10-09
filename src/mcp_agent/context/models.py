from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Span(BaseModel):
    uri: str
    start: int = 0
    end: int = 0
    section: int = 0
    priority: int = 0
    reason: str = ""
    tool: Optional[str] = None
    score: Optional[float] = None


class Slice(BaseModel):
    uri: str
    start: int
    end: int
    bytes: int = 0
    token_estimate: int = 0
    reason: str = ""
    tool: Optional[str] = None


class ManifestMeta(BaseModel):
    pack_hash: Optional[str] = None
    code_version: Optional[str] = None
    tool_versions: Dict[str, str] = Field(default_factory=dict)
    settings_fingerprint: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    inputs_fingerprint: Optional[str] = None


class Manifest(BaseModel):
    slices: List[Slice] = Field(default_factory=list)
    meta: ManifestMeta = Field(default_factory=ManifestMeta)


class AssembleInputs(BaseModel):
    task_targets: List[str] = Field(default_factory=list)
    changed_paths: List[str] = Field(default_factory=list)
    referenced_files: List[str] = Field(default_factory=list)
    failing_tests: List[Dict] = Field(default_factory=list)
    must_include: List[Span] = Field(default_factory=list)
    never_include: List[Span] = Field(default_factory=list)


class AssembleOptions(BaseModel):
    model_config = ConfigDict(extra='allow')
    top_k: int = 25
    neighbor_radius: int = 20
    token_budget: Optional[int] = None
    max_files: Optional[int] = None
    section_caps: Dict[int, int] = Field(default_factory=dict)
    enforce_non_droppable: bool = False
    timeouts_ms: Dict[str, int] = Field(default_factory=dict)


class OverflowItem(BaseModel):
    uri: str
    start: int
    end: int
    reason: str = ""
    tool: Optional[str] = None


class AssembleReport(BaseModel):
    spans_in: int = 0
    spans_merged: int = 0
    files_out: int = 0
    tokens_out: int = 0
    pruned: Dict[str, int] = Field(default_factory=dict)
    overflow: List[OverflowItem] = Field(default_factory=list)
