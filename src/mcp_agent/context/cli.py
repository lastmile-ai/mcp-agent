from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

from .assemble import assemble_context, NoopToolKit
from .models import AssembleInputs, AssembleOptions
from .settings import ContextSettings


def _load_inputs(path: str) -> AssembleInputs:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AssembleInputs.model_validate(data)


def _must_include_covered(inputs: AssembleInputs, manifest) -> List[dict]:
    """Return list of must_include spans that are NOT fully covered by any slice."""
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


def build_opts_from_args(args: argparse.Namespace) -> AssembleOptions:
    return AssembleOptions(
        top_k=args.top_k,
        neighbor_radius=args.neighbor_radius,
        token_budget=args.token_budget,
        max_files=args.max_files,
        section_caps={},  # could be extended via JSON flag if needed
        enforce_non_droppable=False,  # enforcement handled after assembly
        timeouts_ms={
            "semantic": args.semantic_timeout_ms,
            "symbols": args.symbols_timeout_ms,
            "neighbors": args.neighbors_timeout_ms,
            "patterns": args.patterns_timeout_ms,
        },
    )


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="mcp-context", description="ContextPack assembly CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("assemble", help="Assemble a ContextPack from inputs")
    a.add_argument("--inputs", required=True, help="Path to inputs JSON")
    a.add_argument("--out", help="Where to write manifest.json")
    a.add_argument("--dry-run", action="store_true", help="Do not change run state, just print summary")
    a.add_argument("--top-k", type=int, default=25)
    a.add_argument("--neighbor-radius", type=int, default=20)
    a.add_argument("--token-budget", type=int, default=None)
    a.add_argument("--max-files", type=int, default=None)
    a.add_argument("--semantic-timeout-ms", type=int, default=1000)
    a.add_argument("--symbols-timeout-ms", type=int, default=1000)
    a.add_argument("--neighbors-timeout-ms", type=int, default=1000)
    a.add_argument("--patterns-timeout-ms", type=int, default=1000)

    args = p.parse_args(argv)
    if args.cmd == "assemble":
        settings = ContextSettings()
        opts = build_opts_from_args(args)
        inputs = _load_inputs(args.inputs)

        manifest, pack_hash, report = sys.modules[__name__].assemble(inputs, opts)

        # Output
        print(f"pack_hash: {pack_hash}")
        print(json.dumps({"files_out": report.files_out, "tokens_out": report.tokens_out, "pruned": report.pruned}, indent=2))

        # Persist if requested
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(json.dumps(json.loads(manifest.model_dump_json()), indent=2))

        # Enforcement
        missing = _must_include_covered(inputs, manifest)
        if settings.ENFORCE_NON_DROPPABLE and missing:
            print(json.dumps({"non_droppable_missing": missing}, indent=2), file=sys.stderr)
            return 2

        return 0

    return 1  # unreachable


async def _assemble_async(inputs: AssembleInputs, opts: AssembleOptions):
    # Provide a minimal Noop toolkit for CLI; real toolkits are wired in the agent run loop.
    return await assemble_context(inputs, opts, toolkit=NoopToolKit())


def assemble(inputs: AssembleInputs, opts: AssembleOptions):
    # Run the async assembler synchronously for CLI
    import asyncio

    return asyncio.run(_assemble_async(inputs, opts))
