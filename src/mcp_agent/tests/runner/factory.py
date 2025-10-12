"""Runner selection and project detection utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Type

from .base import TestRunner
from .spec import TestRunnerSpec
from . import adapters


RUNNER_CLASSES: Mapping[str, Type[TestRunner]] = {
    "python": adapters.PyTestRunner,
    "javascript": adapters.JavaScriptRunner,
    "java": adapters.JavaRunner,
    "go": adapters.GoTestRunner,
    "bash": adapters.BashTestRunner,
    "rust": adapters.RustTestRunner,
}


def detect_project_language(project_root: Path) -> str | None:
    root = project_root.resolve()
    manifest_checks = [
        ("python", ["pyproject.toml", "pytest.ini", "setup.cfg"]),
        ("javascript", ["package.json", "pnpm-lock.yaml", "yarn.lock"]),
        ("go", ["go.mod"]),
        ("java", ["pom.xml", "build.gradle", "build.gradle.kts"]),
        ("rust", ["Cargo.toml"]),
        ("bash", [".sh", ".bats"]),
    ]
    for language, manifests in manifest_checks:
        for manifest in manifests:
            if manifest.startswith("."):
                if any(path.suffix == manifest for path in root.glob("**/*")):
                    return language
            else:
                if (root / manifest).exists():
                    return language
    return None


def select_runner(spec: TestRunnerSpec) -> TestRunner:
    language = (spec.language or (spec.project_root and detect_project_language(spec.project_root)) or "python").lower()
    runner_cls = RUNNER_CLASSES.get(language)
    if runner_cls is None:
        raise ValueError(f"unsupported_language:{language}")
    return runner_cls()


__all__ = ["select_runner", "detect_project_language", "RUNNER_CLASSES"]
