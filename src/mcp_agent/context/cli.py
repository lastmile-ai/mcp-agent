from __future__ import annotations
import argparse
import json
import sys
from typing import List, Optional

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
        max_depth=args.max_depth,
        seed_weights=args.seed_weights,
        neighbor_weights=args.neighbor_weights,
        allow_wildcards=not args.no_wildcards,
        dynamic_chunk_window=args.dynamic_chunk_window,
    )

def _main_impl(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="Assemble context from definitions")
    parser.add_argument("--inputs", required=True, help="Path to JSON with AssembleInputs")
    parser.add_argument(
        "--settings", default="context_settings.yaml", help="Path to settings YAML"
    )
    parser.add_argument("--top_k", type=int, help="Override top_k")
    parser.add_argument("--neighbor_radius", type=int, help="Override neighbor_radius")
    parser.add_argument("--max_depth", type=int, help="Override max_depth")
    parser.add_argument("--seed_weights", help="Override seed_weights (float or map)")
    parser.add_argument("--neighbor_weights", help="Override neighbor_weights")
    parser.add_argument("--no_wildcards", action="store_true", help="Disable wildcards")
    parser.add_argument(
        "--dynamic_chunk_window", type=int, help="Override dynamic_chunk_window"
    )

    args = parser.parse_args(argv)

    inputs = _load_inputs(args.inputs)
    settings = ContextSettings.from_yaml(args.settings)

    opts = build_opts_from_args(args)
    tool_kit = NoopToolKit()

    manifest = assemble_context(inputs, settings, opts, tool_kit)

    missing = _must_include_covered(inputs, manifest)
    if missing:
        print(
            f"ERROR: {len(missing)} must_include span(s) not fully covered:",
            file=sys.stderr,
        )
        for m in missing:
            print(
                f"  {m['uri']} [{m['start']}-{m['end']}] - {m['reason']}", file=sys.stderr
            )
        sys.exit(1)

    print(json.dumps(manifest.model_dump(), indent=2))

def main(argv: Optional[List[str]] = None) -> int:
    return _main_impl(argv)
if __name__ == "__main__":
    main()
