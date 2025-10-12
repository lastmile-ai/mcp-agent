from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

from .assemble import assemble_context, NoopToolKit, must_include_missing
from .errors import BudgetError
from .models import AssembleInputs, AssembleOptions
from .settings import ContextSettings


def _load_inputs(path: str) -> AssembleInputs:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return AssembleInputs.model_validate(data)


def build_opts_from_args(args: argparse.Namespace, settings: ContextSettings) -> AssembleOptions:
    opts = AssembleOptions(
        top_k=args.top_k if args.top_k is not None else settings.TOP_K,
        neighbor_radius=args.neighbor_radius if args.neighbor_radius is not None else settings.NEIGHBOR_RADIUS,
        token_budget=args.token_budget if args.token_budget is not None else settings.TOKEN_BUDGET,
        max_files=args.max_files if args.max_files is not None else settings.MAX_FILES,
        section_caps=dict(settings.SECTION_CAPS or {}),
        enforce_non_droppable=settings.ENFORCE_NON_DROPPABLE,
    )

    for item in args.section_cap or []:
        section, _, limit = item.partition("=")
        if not section or not limit:
            raise ValueError(f"Invalid --section-cap value: '{item}'")
        opts.section_caps[int(section)] = int(limit)

    if args.enforce_non_droppable:
        opts.enforce_non_droppable = True
    if args.disable_enforce_non_droppable:
        opts.enforce_non_droppable = False

    return opts


def _cmd_assemble(args: argparse.Namespace) -> int:
    try:
        inputs = _load_inputs(args.inputs)
    except FileNotFoundError:
        print(f"ERROR: inputs file not found: {args.inputs}", file=sys.stderr)
        return 1

    settings = ContextSettings()

    try:
        opts = build_opts_from_args(args, settings)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        manifest, pack_hash, report = asyncio.run(
            assemble_context(
                inputs=inputs,
                opts=opts,
                toolkit=NoopToolKit(),
            )
        )
    except BudgetError as exc:
        print("ERROR: Resource budget exceeded during assembly", file=sys.stderr)
        for item in exc.overflow:
            uri = item.get("uri") if isinstance(item, dict) else item
            reason = item.get("reason") if isinstance(item, dict) else ""
            print(f"  {uri} - {reason}", file=sys.stderr)
        return 2

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(manifest.model_dump(), indent=2)
        out_path.write_text(payload, encoding="utf-8")

    print(f"pack_hash: {pack_hash}")
    print(f"files_out: {report.files_out}")
    print(f"tokens_out: {report.tokens_out}")

    enforce = opts.enforce_non_droppable
    if enforce:
        missing = must_include_missing(inputs, manifest)
        if missing:
            print(
                f"ERROR: {len(missing)} must_include span(s) not fully covered:",
                file=sys.stderr,
            )
            for entry in missing:
                print(
                    f"  {entry['uri']} [{entry['start']}-{entry['end']}] - {entry['reason']}",
                    file=sys.stderr,
                )
            return 2

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble context manifests")
    subparsers = parser.add_subparsers(dest="command")

    assemble_parser = subparsers.add_parser("assemble", help="assemble context pack")
    assemble_parser.add_argument("--inputs", required=True, help="Path to AssembleInputs JSON")
    assemble_parser.add_argument("--out", help="Path to write manifest JSON")
    assemble_parser.add_argument("--dry-run", action="store_true", help="Simulate assembly without side effects")
    assemble_parser.add_argument("--top-k", type=int, help="Override top_k")
    assemble_parser.add_argument("--neighbor-radius", type=int, help="Override neighbor radius")
    assemble_parser.add_argument("--token-budget", type=int, help="Override token budget")
    assemble_parser.add_argument("--max-files", type=int, help="Override max files")
    assemble_parser.add_argument(
        "--section-cap",
        action="append",
        metavar="SECTION=LIMIT",
        default=[],
        help="Override section cap (e.g. 2=1)",
    )
    assemble_parser.add_argument(
        "--enforce-non-droppable",
        action="store_true",
        help="Fail if must_include spans are not fully covered",
    )
    assemble_parser.add_argument(
        "--no-enforce-non-droppable",
        dest="disable_enforce_non_droppable",
        action="store_true",
        help="Disable non-droppable enforcement",
    )
    assemble_parser.set_defaults(func=_cmd_assemble)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
