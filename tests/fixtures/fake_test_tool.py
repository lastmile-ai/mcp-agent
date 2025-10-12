#!/usr/bin/env python3
"""Utility used by tests to simulate different language test runners."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring


def build_xml(cases: list[tuple[str, str, str | None]]):
    suite = Element("testsuite", attrib={
        "name": "fake-suite",
        "tests": str(len(cases)),
        "failures": str(sum(1 for _, status, _ in cases if status == "failed")),
        "errors": str(sum(1 for _, status, _ in cases if status == "error")),
        "skipped": str(sum(1 for _, status, _ in cases if status == "skipped")),
    })
    for name, status, message in cases:
        case = SubElement(suite, "testcase", attrib={"name": name, "classname": "fake"})
        if status == "failed":
            SubElement(case, "failure", attrib={"message": message or "failed"})
        elif status == "error":
            SubElement(case, "error", attrib={"message": message or "error"})
        elif status == "skipped":
            SubElement(case, "skipped", attrib={"message": message or "skipped"})
    return b"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + tostring(suite)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", required=True)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--skip", action="store_true")
    args = parser.parse_args()

    cases = [(f"{args.language}::test_pass", "passed", None)]
    if args.skip:
        cases.append((f"{args.language}::test_skip", "skipped", "skipped"))
    if args.fail:
        cases.append((f"{args.language}::test_fail", "failed", "failure"))

    for name, status, message in cases:
        suffix = status.upper()
        detail = f" - {message}" if message else ""
        print(f"{name} ... {suffix}{detail}")

    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        args.junit.write_bytes(build_xml(cases))

    return 1 if args.fail else 0


if __name__ == "__main__":
    sys.exit(main())
