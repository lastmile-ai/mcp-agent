"""Helpers for parsing and synthesising JUnit XML across adapters."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Tuple

from .result import NormalizedTestCase, NormalizedTestRun, NormalizedTestSuite


_TESTCASE_PATTERN = re.compile(
    r"^(?P<name>[\w\.\-/:]+)\s*(?:\.\.\.\s*|:\s*)(?P<status>PASS|FAIL|ERROR|SKIP|XFAIL|XPASS)(?:\s*[:\-]\s*(?P<message>.+))?",
    re.IGNORECASE,
)


def parse_or_synthesise_junit(junit_path: Path | None, stdout: str, stderr: str, exit_code: int) -> Tuple[str, NormalizedTestRun]:
    """Return xml text and a normalized representation."""

    if junit_path and junit_path.exists():
        xml_text = junit_path.read_text(encoding="utf-8")
    else:
        xml_text = synthesise_junit(stdout, stderr, exit_code)
    normalized = _normalise_xml(xml_text)
    return xml_text, normalized


def synthesise_junit(stdout: str, stderr: str, exit_code: int) -> str:
    cases: List[Tuple[str, str, str | None]] = []
    for line in stdout.splitlines():
        match = _TESTCASE_PATTERN.match(line.strip())
        if match:
            status = match.group("status").lower()
            status = {
                "pass": "passed",
                "fail": "failed",
                "error": "error",
                "skip": "skipped",
                "xfail": "skipped",
                "xpass": "failed",
            }.get(status, "passed")
            cases.append((match.group("name"), status, match.group("message")))
    if not cases:
        status = "passed" if exit_code == 0 else "failed"
        message = stderr.strip() or stdout.strip()
        cases.append(("synthetic", status, message or None))
    tests = len(cases)
    failures = sum(1 for _, status, _ in cases if status == "failed")
    errors = sum(1 for _, status, _ in cases if status == "error")
    skipped = sum(1 for _, status, _ in cases if status == "skipped")
    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<testsuite name=\"synthetic\" tests=\"{tests}\" failures=\"{failures}\" errors=\"{errors}\" skipped=\"{skipped}\">".format(
            tests=tests, failures=failures, errors=errors, skipped=skipped
        ),
    ]
    for name, status, message in cases:
        lines.append(f"  <testcase classname=\"synthetic\" name=\"{_xml_escape(name)}\">")
        if status == "failed":
            msg = _xml_escape(message or "Test failed")
            lines.append(f"    <failure message=\"{msg}\" />")
        elif status == "error":
            msg = _xml_escape(message or "Test error")
            lines.append(f"    <error message=\"{msg}\" />")
        elif status == "skipped":
            msg = _xml_escape(message or "Skipped")
            lines.append(f"    <skipped message=\"{msg}\" />")
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    return "\n".join(lines)


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("\"", "&quot;")
        .replace("'", "&apos;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _normalise_xml(xml_text: str) -> NormalizedTestRun:
    root = ET.fromstring(xml_text)
    if root.tag == "testsuites":
        suite_elements = root.findall("testsuite")
    elif root.tag == "testsuite":
        suite_elements = [root]
    else:
        suite_elements = root.findall(".//testsuite")
    suites: List[NormalizedTestSuite] = []
    for suite in suite_elements:
        name = suite.attrib.get("name", "suite")
        tests = int(suite.attrib.get("tests", 0) or 0)
        failures = int(suite.attrib.get("failures", 0) or 0)
        errors = int(suite.attrib.get("errors", 0) or 0)
        skipped = int(suite.attrib.get("skipped", 0) or 0)
        time = suite.attrib.get("time")
        try:
            duration = float(time) if time is not None else None
        except ValueError:
            duration = None
        cases: List[NormalizedTestCase] = []
        for case in suite.findall("testcase"):
            status = "passed"
            message: str | None = None
            if case.find("failure") is not None:
                status = "failed"
                message = case.find("failure").attrib.get("message")
            elif case.find("error") is not None:
                status = "error"
                message = case.find("error").attrib.get("message")
            elif case.find("skipped") is not None:
                status = "skipped"
                message = case.find("skipped").attrib.get("message")
            case_time = case.attrib.get("time")
            try:
                case_duration = float(case_time) if case_time is not None else None
            except ValueError:
                case_duration = None
            cases.append(
                NormalizedTestCase(
                    name=case.attrib.get("name", "case"),
                    classname=case.attrib.get("classname"),
                    status=status,
                    message=message,
                    duration=case_duration,
                )
            )
        suites.append(
            NormalizedTestSuite(
                name=name,
                tests=tests or len(cases),
                failures=failures,
                errors=errors,
                skipped=skipped,
                time=duration,
                cases=cases,
            )
        )
    return NormalizedTestRun(suites=suites)


def junit_sha256(xml_text: str) -> str:
    return hashlib.sha256(xml_text.encode("utf-8")).hexdigest()


__all__ = ["parse_or_synthesise_junit", "junit_sha256"]
