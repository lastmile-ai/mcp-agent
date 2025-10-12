# Multi-language Test Runner

The MCP Agent test runner abstracts execution across Python, JavaScript, Java, Go, Rust, and Bash projects. It normalizes outputs into a single schema, generates or synthesizes JUnit XML, and persists all run artifacts for CI pipelines and manual inspection.

## Features

- **Adapter registry** – Each supported language maps to a dedicated adapter (e.g. `PyTestRunner`, `JavaScriptRunner`, `JavaRunner`, `GoTestRunner`, `RustTestRunner`, `BashTestRunner`).
- **Auto-detection** – Projects can omit the `language` attribute; the runner inspects manifests such as `pyproject.toml`, `package.json`, `pom.xml`, `go.mod`, `Cargo.toml`, or shell scripts to determine an adapter.
- **Configurable commands** – Override defaults with custom commands, environment variables, timeouts, and JUnit output locations.
- **JUnit normalization** – Parses native XML or synthesizes reports from stdout/stderr using regex heuristics so downstream tooling receives a consistent structure.
- **Artifact persistence** – Saves stdout, stderr, normalized JUnit XML, and metadata for each run under `ARTIFACTS_ROOT` (or a provided artifact root) and records telemetry events summarizing the execution.
- **Telemetry** – Emits a `test_run` event containing the runner name, result, duration, exit code, artifact names, and a SHA256 hash of the JUnit payload.

## Quickstart

```python
from pathlib import Path

from mcp_agent.tests.runner import TestRunnerManager, TestRunnerSpec

manager = TestRunnerManager(artifact_root=Path("./artifacts"))
result = manager.run(
    TestRunnerSpec(
        project_root=Path("./examples/javascript"),
        # language="javascript",  # optional when a manifest is present
        env={"CI": "true"},
    )
)

print(result.normalized.summary)
print(result.artifacts)
```

## Adapter Defaults

| Language     | Adapter             | Default Command                                | Default JUnit Path                                  |
| ------------ | ------------------- | ---------------------------------------------- | --------------------------------------------------- |
| Python       | `PyTestRunner`      | `pytest -q --disable-warnings --junit-xml …`   | `.mcp-agent/test-results/python-junit.xml`          |
| JavaScript   | `JavaScriptRunner`  | `npm test`                                     | `.mcp-agent/test-results/javascript-junit.xml`      |
| Java         | `JavaRunner`        | `./gradlew test` (if present) else `mvn test`  | `.mcp-agent/test-results/java-junit.xml`            |
| Go           | `GoTestRunner`      | `go test ./... -json`                          | `.mcp-agent/test-results/go-junit.xml`              |
| Rust         | `RustTestRunner`    | `cargo test --all --message-format=json`       | `.mcp-agent/test-results/rust-junit.xml`            |
| Bash         | `BashTestRunner`    | `bash run-tests.sh`                            | `.mcp-agent/test-results/bash-junit.xml`            |

Use `TestRunnerSpec.commands` to override any command; specify multiple commands to run sequentially. Pass `junit_path` when a tool already emits XML to avoid synthesizing from stdout.

## Artifact Layout

Artifacts are stored under `<artifact_root>/<run_id>/`:

- `test-stdout.log` – raw stdout
- `test-stderr.log` – raw stderr
- `test-junit.xml` – normalized or synthesized JUnit payload
- `test-meta.json` – metadata including command, language, duration, exit code, working directory, and original JUnit location

Set the environment variable `ARTIFACTS_ROOT` or pass `artifact_root` to `TestRunnerManager`/`TestRunnerConfig` to control the root directory.

## CI Matrix Strategy

Run adapters against language fixtures in your CI pipeline to guarantee coverage:

```yaml
jobs:
  test-runners:
    strategy:
      matrix:
        language: [python, javascript, java, go, bash, rust]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: pip install .[dev]
      - run: |
          python - <<'PY'
          from pathlib import Path
          from mcp_agent.tests.runner import TestRunnerManager, TestRunnerSpec

          manager = TestRunnerManager(artifact_root=Path("./artifacts"))
          spec = TestRunnerSpec(project_root=Path(f"tests/fixtures/{'${{matrix.language}}'}_project"))
          result = manager.run(spec)
          print(result.normalized.summary)
          PY
      - uses: actions/upload-artifact@v4
        with:
          name: test-artifacts-${{ matrix.language }}
          path: artifacts
```

## Extending Adapters

1. Implement a new adapter subclassing `TestRunner` and register it in `RUNNER_CLASSES`.
2. Provide defaults for commands and JUnit paths and update detection logic if required.
3. Add fixture projects and integration tests under `tests/` to validate detection, artifact persistence, and JUnit normalization.
4. Document the adapter and ensure CI coverage.

## Telemetry

The runner logs structured events under the `mcp_agent.tests.runner` logger. Each event includes:

- `event`: `"test_run"`
- `runner`: adapter language (e.g., `python`)
- `result`: `success` or `failure`
- `duration_seconds`
- `exit_code`
- `artifacts`: persisted artifact file names
- `junit_hash`: SHA256 of the normalized JUnit XML
- Optional `attributes`: custom telemetry attributes supplied via `TestRunnerConfig`

Integrate these events with your existing logging or OpenTelemetry exporters to monitor pass/fail rates and artifact persistence.
