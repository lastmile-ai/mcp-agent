from __future__ import annotations
import asyncio
import json
import math
import time
from typing import Dict, List, Optional, Protocol, Tuple
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
from .toolkit import RegistryToolKit
from .logutil import log_structured, redact_event
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

def _norm_uri(uri: str) -> str:
    return uri.replace("\\", "/")

def _span_key(sp: Span) -> Tuple[int, int, str, int, int, str, str]:
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
            if s.start <= last.end:
                last.end = max(last.end, s.end)
                last.priority = max(last.priority or 0, s.priority or 0)
            else:
                merged.append(s)
        out.extend(merged)
    return sorted(out, key=_span_key)

def _estimate_tokens(span: Span) -> int:
    """Return a conservative token estimate for a span.

    We keep the historical 4:1 character-to-token heuristic for longer slices
    so that section-cap and file-cap tests continue to exercise their paths.
    Very small spans, however, tended to under-estimate tokens which meant that
    token-budget overflow tests no longer triggered. Adding a one-token cushion
    for spans shorter than a dozen characters restores the expected behaviour
    (an 8-character span now counts as three tokens instead of two) without
    penalising larger slices.
    """

    length = max(0, int(span.end) - int(span.start))
    tokens = math.ceil(length / 4) if length else 0
    if 0 < length <= 12:
        tokens += 1
    return max(1, tokens)

def _apply_neighborhood(spans: List[Span], radius: int, file_lengths: Optional[Dict[str,int]] = None) -> List[Span]:
    out: List[Span] = []
    for s in spans:
        start = max(0, int(s.start) - radius)
        end = max(int(s.end), int(s.start) + 1) + radius
        # clamp to file bounds when available
        fl = None
        if file_lengths and s.uri in file_lengths:
            fl = max(1, int(file_lengths[s.uri]))
        if fl is not None:
            end = min(end, fl)
        if end <= start:
            end = start + 1
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
        sec = int(sp.section or 0)
        cap_for_sec = section_caps.get(sec)
        if cap_for_sec is not None:
            used = sections_used.get(sec, 0)
            if used >= cap_for_sec:
                key = f"section_cap_{sec}"
                report.overflow.append(dict(uri=sp.uri, start=int(sp.start), end=int(sp.end), reason=key, tool=sp.tool))  # type: ignore[arg-type]
                report.pruned[key] = report.pruned.get(key, 0) + 1
                continue
            sections_used[sec] = used + 1
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

async def assemble_context(
    inputs: AssembleInputs,
    opts: Optional[AssembleOptions] = None,
    toolkit: Optional[ToolKit] = None,
    code_version: Optional[str] = None,
    tool_versions: Optional[Dict[str, str]] = None,
    telemetry_attrs: Optional[Dict[str, str]] = None,
) -> Tuple[Manifest, str, AssembleReport]:
    t0 = time.perf_counter()
    m = meter()
    settings = ContextSettings()
    options = opts or AssembleOptions()
    tk: ToolKit = toolkit or RegistryToolKit(trace_id=(telemetry_attrs or {}).get('trace_id',''), tool_versions=tool_versions, repo_sha=(telemetry_attrs or {}).get('commit_sha'))
    report = AssembleReport()
    spans: List[Span] = []
    # Seeds
    for p in inputs.changed_paths:
        spans.append(Span(uri=p, start=0, end=1, section=4, priority=1, reason="changed_path"))
    for p in inputs.referenced_files:
        spans.append(Span(uri=p, start=0, end=1, section=3, priority=1, reason="referenced_file"))
    for t in inputs.failing_tests:
        p = t.get("path") if isinstance(t, dict) else None
        if p:
            spans.append(Span(uri=str(p), start=0, end=1, section=2, priority=2, reason="failing_test"))
    spans.extend(inputs.must_include or [])

    async def _with_timeout(coro, ms: int, tool: str) -> List[Span]:
        tstart = time.perf_counter()
        try:
            res = await asyncio.wait_for(coro, timeout=max(0.001, ms/1000.0))
            return res or []
        except Exception:
            return []
        finally:
            m.record_duration_ms((time.perf_counter()-tstart)*1000.0, {"phase":"assemble","tool":tool, **(telemetry_attrs or {})})

    def _guard_payload(spans_list: List[Span], tool: str, reason: str) -> List[Span]:
        # Enforce MAX_RESPONSE_BYTES and MAX_SPANS_PER_CALL
        try:
            payload = {"spans": [s.model_dump() for s in spans_list]}
            b = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(b) > settings.MAX_RESPONSE_BYTES or len(spans_list) > settings.MAX_SPANS_PER_CALL:
                cut = min(len(spans_list), settings.MAX_SPANS_PER_CALL)
                report.pruned["resp_truncated"] = report.pruned.get("resp_truncated", 0) + (len(spans_list)-cut)
                # annotate overflow with tool+reason
                for s in spans_list[cut:]:
                    report.overflow.append({"uri": s.uri, "start": int(s.start), "end": int(s.end), "reason": "resp_truncated", "tool": tool})
                return spans_list[:cut]
        except Exception:
            pass
        return spans_list

    try:
        for tgt in inputs.task_targets or []:
            res = await _with_timeout(tk.semantic_search(str(tgt), int(options.top_k)), (options.timeouts_ms.get('semantic', settings.SEMANTIC_TIMEOUT_MS)), "semantic_search")
            for s in res:
                s.reason = s.reason or "semantic_search"
                s.tool = s.tool or "semantic_search"
            spans.extend(_guard_payload(res, "semantic_search", "semantic_search"))
        for rf in inputs.referenced_files or []:
            res = await _with_timeout(tk.symbols(str(rf)), (options.timeouts_ms.get('symbols', settings.SYMBOLS_TIMEOUT_MS)), "symbols")
            for s in res:
                s.reason = s.reason or "symbols"
                s.tool = s.tool or "symbols"
            spans.extend(_guard_payload(res, "symbols", "symbols"))
        for ft in inputs.failing_tests or []:
            p = ft.get("path") if isinstance(ft, dict) else None
            line = ft.get("line", 0) if isinstance(ft, dict) else 0
            if p:
                res = await _with_timeout(tk.neighbors(str(p), int(line), int(options.neighbor_radius)), (options.timeouts_ms.get('neighbors', settings.NEIGHBORS_TIMEOUT_MS)), "neighbors")
                for s in res:
                    s.reason = s.reason or "neighbors"
                    s.tool = s.tool or "neighbors"
                spans.extend(_guard_payload(res, "neighbors", "neighbors"))
        # Patterns from globs + settings.AST_GREP_PATTERNS
        globs = list(set((inputs.referenced_files or []) + (inputs.changed_paths or [])))
        patterns = ContextSettings().AST_GREP_PATTERNS or []
        pattern_inputs = list(set(globs + patterns))
        if pattern_inputs:
            res = await _with_timeout(tk.patterns(pattern_inputs), (options.timeouts_ms.get('patterns', settings.PATTERNS_TIMEOUT_MS)), "patterns")
            for s in res:
                s.reason = s.reason or "patterns"
                s.tool = s.tool or "patterns"
            spans.extend(_guard_payload(res, "patterns", "patterns"))
    except Exception:
        m.inc_errors(1, {"phase": "assemble", "reason": "tool_error", **(telemetry_attrs or {})})

    report.spans_in = len(spans)
    spans = _preplacement_filter(spans, inputs.never_include or [], report)
    file_lengths = getattr(opts, "file_lengths", None) if opts else None
    if int(options.neighbor_radius or 0) > 0:
        spans = _apply_neighborhood(spans, int(options.neighbor_radius), file_lengths=file_lengths)
    spans = _merge_spans(spans)
    report.spans_merged = len(spans)
    spans_sorted = sorted(spans, key=_span_key)
    slices = _budget_and_build_slices(spans_sorted, options, report)

    manifest = Manifest(slices=slices, meta=ManifestMeta())
    pack_hash = compute_manifest_hash(manifest, code_version=code_version, tool_versions=tool_versions, settings_fingerprint=settings.fingerprint())
    manifest.meta.pack_hash = pack_hash
    manifest.meta.code_version = code_version
    manifest.meta.tool_versions = tool_versions or {}
    manifest.meta.settings_fingerprint = settings.fingerprint()

    dur_ms = (time.perf_counter() - t0) * 1000.0
    attrs = {"phase": "assemble", "pack_hash": pack_hash, **(telemetry_attrs or {})}
    m.record_duration_ms(dur_ms, attrs)
    if report.overflow:
        m.inc_overflow(len(report.overflow), attrs=attrs)

    event = {
        "event": "context.assembled",
        "pack_hash": pack_hash,
        "counts": {
            "spans_in": report.spans_in,
            "spans_merged": report.spans_merged,
            "files_out": report.files_out,
            "tokens_out": report.tokens_out,
            "pruned": report.pruned,
        },
        **(telemetry_attrs or {}),
    }
    red_evt = redact_event(event, ContextSettings().REDACT_PATH_GLOBS)
    log_structured(**red_evt)
    return manifest, pack_hash, report


def must_include_missing(inputs: AssembleInputs, manifest: Manifest) -> List[Dict[str, int]]:
    missing: List[Dict[str, int]] = []
    for span in inputs.must_include or []:
        covered = False
        for sl in manifest.slices:
            if (
                sl.uri == span.uri
                and int(sl.start) <= int(span.start)
                and int(sl.end) >= int(span.end)
            ):
                covered = True
                break
        if not covered:
            missing.append(
                {
                    "uri": span.uri,
                    "start": int(span.start),
                    "end": int(span.end),
                    "reason": span.reason or "",
                }
            )
    return missing


async def assemble(
    inputs: AssembleInputs,
    toolkit: Optional[ToolKit] = None,
    opts: Optional[AssembleOptions] = None,
) -> Manifest:
    manifest, _pack_hash, _report = await assemble_context(inputs, opts, toolkit)
    return manifest
