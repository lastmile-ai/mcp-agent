from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from .models import (
    AssembleInputs,
    AssembleOptions,
    AssembleReport,
    Manifest,
    ManifestMeta,
    Slice,
    Span,
)
from .settings import ContextSettings
from .hash import compute_manifest_hash
from .telemetry import meter


# ---- Toolkit protocol and default ----

class ToolKit(Protocol):
    async def semantic_search(self, query: str, top_k: int) -> List[Span]: ...
    async def symbols(self, target: str) -> List[Span]: ...
    async def neighbors(self, uri: str, line_or_start: int, radius: int) -> List[Span]: ...
    async def patterns(self, globs: List[str]) -> List[Span]: ...


class NoopToolKit:
    async def semantic_search(self, query: str, top_k: int) -> List[Span]:
        return []
    async def symbols(self, target: str) -> List[Span]:
        return []
    async def neighbors(self, uri: str, line_or_start: int, radius: int) -> List[Span]:
        return []
    async def patterns(self, globs: List[str]) -> List[Span]:
        return []


# ---- Helpers ----

def _norm_uri(uri: str) -> str:
    # Minimal normalization; assume upstream provides file:// URIs
    return uri.replace("\\", "/")

def _span_key(sp: Span) -> Tuple[int, int, str, int, int, str, str]:
    # Stable ordering: section asc, priority desc, uri asc, start asc, end asc, reason asc, tool asc
    return (
        int(sp.section or 0),
        -int(sp.priority or 0),
        _norm_uri(sp.uri or ""),
        int(sp.start or 0),
        int(sp.end or 0),
        sp.reason or "",
        sp.tool or "",
    )

def _merge_spans(spans: List[Span]) -> List[Span]:
    # Merge overlapping spans per URI. Keep earliest start and latest end. Preserve highest priority and first reason/tool.
    by_uri: Dict[str, List[Span]] = {}
    for sp in spans:
        by_uri.setdefault(_norm_uri(sp.uri), []).append(sp)

    out: List[Span] = []
    for uri, lst in by_uri.items():
        lst_sorted = sorted(lst, key=lambda s: (s.start, s.end))
        merged: List[Span] = []
        for s in lst_sorted:
            if not merged:
                merged.append(s)
                continue
            last = merged[-1]
            if s.start <= last.end:  # overlap or touch
                # merge
                last.end = max(last.end, s.end)
                last.priority = max(last.priority or 0, s.priority or 0)
                # keep existing reason/tool/section/score
            else:
                merged.append(s)
        out.extend(merged)
    # Final stable order
    return sorted(out, key=_span_key)

def _estimate_tokens(span: Span) -> int:
    # Heuristic: 1 token ~= 4 chars. If we have byte-span length use it, else default to radius*10
    length = max(0, int(span.end) - int(span.start))
    # Avoid zero to keep budgets meaningful
    return max(1, math.ceil(length / 4))

def _apply_neighborhood(spans: List[Span], radius: int) -> List[Span]:
    out: List[Span] = []
    for s in spans:
        start = max(0, int(s.start) - radius)
        end = max(int(s.end), int(s.start) + 1) + radius
        out.append(Span(uri=s.uri, start=start, end=end, section=s.section, priority=s.priority,
                        reason=s.reason or "neighbor", tool=s.tool, score=s.score))
    return out

def _preplacement_filter(spans: List[Span], never: List[Span], report: AssembleReport) -> List[Span]:
    never_set = {( _norm_uri(n.uri), int(n.start), int(n.end) ) for n in never}
    out: List[Span] = []
    for s in spans:
        key = (_norm_uri(s.uri), int(s.start), int(s.end))
        if key in never_set:
            report.pruned["never_include"] = report.pruned.get("never_include", 0) + 1
            continue
        out.append(s)
    return out

def _budget_and_build_slices(spans: List[Span], opts: AssembleOptions, report: AssembleReport) -> List[Slice]:
    # Build slices honoring caps: token_budget, max_files, section_caps.
    # We assume tokens per span via heuristic. In real impl we would measure file bytes or tokens.
    section_caps = opts.section_caps or {}
    files_seen: Dict[str, int] = {}
    sections_used: Dict[int, int] = {}
    tokens_used = 0

    slices: List[Slice] = []
    for sp in spans:
        tokens = _estimate_tokens(sp)
        if opts.token_budget is not None and tokens_used + tokens > int(opts.token_budget):
            report.overflow.append(dict(uri=sp.uri, start=int(sp.start), end=int(sp.end), reason="token_budget", tool=sp.tool))  # type: ignore[arg-type]
            report.pruned["token_budget"] = report.pruned.get("token_budget", 0) + 1
            continue

        # per-section cap
        sec = int(sp.section or 0)
        cap_for_sec = section_caps.get(sec)
        if cap_for_sec is not None:
            used = sections_used.get(sec, 0)
            if used >= cap_for_sec:
                report.overflow.append(dict(uri=sp.uri, start=int(sp.start), end=int(sp.end), reason=f"section_cap_{sec}", tool=sp.tool))  # type: ignore[arg-type]
                report.pruned[f"section_cap_{sec}"] = report.pruned.get(f"section_cap_{sec}", 0) + 1
                continue
            sections_used[sec] = used + 1

        # max files cap
        if opts.max_files is not None:
            if files_seen.get(sp.uri, 0) == 0 and len(files_seen) >= int(opts.max_files):
                report.overflow.append(dict(uri=sp.uri, start=int(sp.start), end=int(sp.end), reason="max_files", tool=sp.tool))  # type: ignore[arg-type]
                report.pruned["max_files"] = report.pruned.get("max_files", 0) + 1
                continue

        files_seen[sp.uri] = 1
        tokens_used += tokens
        slices.append(Slice(uri=sp.uri, start=int(sp.start), end=int(sp.end), bytes=tokens*4, token_estimate=tokens, reason=sp.reason or "", tool=sp.tool))

    report.tokens_out = tokens_used
    report.files_out = len({s.uri for s in slices})
    return slices


# ---- Public API ----

async def assemble_context(
    inputs: AssembleInputs,
    opts: Optional[AssembleOptions] = None,
    toolkit: Optional[ToolKit] = None,
    code_version: Optional[str] = None,
    tool_versions: Optional[Dict[str, str]] = None,
) -> Tuple[Manifest, str, AssembleReport]:
    """
    Deterministic context assembly with capability gates and budgets.
    Returns (manifest, pack_hash, report). No network calls if toolkit is None.
    """
    t0 = time.perf_counter()
    m = meter()
    settings = ContextSettings()
    options = opts or AssembleOptions()
    tk: ToolKit = toolkit or NoopToolKit()

    report = AssembleReport()
    spans: List[Span] = []

    # Seed from inputs
    for p in inputs.changed_paths:
        spans.append(Span(uri=p, start=0, end=1, section=4, priority=1, reason="changed_path"))
    for p in inputs.referenced_files:
        spans.append(Span(uri=p, start=0, end=1, section=3, priority=1, reason="referenced_file"))
    for t in inputs.failing_tests:
        p = t.get("path") if isinstance(t, dict) else None
        if p:
            spans.append(Span(uri=str(p), start=0, end=1, section=2, priority=2, reason="failing_test"))

    # must/never provided by caller
    spans.extend(inputs.must_include or [])

    # Capability gates: run tool calls if available, but tolerate absence
    try:
        # semantic search from task targets
        for tgt in inputs.task_targets or []:
            try:
                res = await tk.semantic_search(str(tgt), int(options.top_k))
                for s in res:
                    s.reason = s.reason or "semantic_search"
                    s.tool = s.tool or "semantic_search"
                spans.extend(res or [])
            except Exception:
                pass

        # symbols for referenced files
        for rf in inputs.referenced_files or []:
            try:
                res = await tk.symbols(str(rf))
                for s in res:
                    s.reason = s.reason or "symbols"
                    s.tool = s.tool or "symbols"
                spans.extend(res or [])
            except Exception:
                pass

        # neighbors for failing tests
        for ft in inputs.failing_tests or []:
            p = ft.get("path") if isinstance(ft, dict) else None
            line = ft.get("line", 0) if isinstance(ft, dict) else 0
            if p:
                try:
                    res = await tk.neighbors(str(p), int(line), int(options.neighbor_radius))
                    for s in res:
                        s.reason = s.reason or "neighbors"
                        s.tool = s.tool or "neighbors"
                    spans.extend(res or [])
                except Exception:
                    pass
    except Exception as e:
        # Defensive: never break determinism on tool errors
        m.inc_errors(1, {"phase": "assemble", "reason": "tool_error"})
        # continue with what we have

    report.spans_in = len(spans)

    # Pre-placement never_include filter
    spans = _preplacement_filter(spans, inputs.never_include or [], report)

    # Neighborhood expansion
    if int(options.neighbor_radius or 0) > 0:
        spans = _apply_neighborhood(spans, int(options.neighbor_radius))

    # Merge and dedupe
    spans = _merge_spans(spans)
    report.spans_merged = len(spans)

    # Stable order
    spans_sorted = sorted(spans, key=_span_key)

    # Budgeting and slices
    slices = _budget_and_build_slices(spans_sorted, options, report)

    manifest = Manifest(slices=slices, meta=ManifestMeta())
    # Hash with settings fingerprint
    pack_hash = compute_manifest_hash(manifest, code_version=code_version, tool_versions=tool_versions, settings_fingerprint=settings.fingerprint())
    manifest.meta.pack_hash = pack_hash
    manifest.meta.code_version = code_version
    manifest.meta.tool_versions = tool_versions or {}
    manifest.meta.settings_fingerprint = settings.fingerprint()

    # Emit metrics
    dur_ms = (time.perf_counter() - t0) * 1000.0
    m.record_duration_ms(dur_ms, {"phase": "assemble"})
    if report.overflow:
        m.inc_overflow(len(report.overflow), {"phase": "assemble"})

    return manifest, pack_hash, report
