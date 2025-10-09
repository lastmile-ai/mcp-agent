import json
from importlib import import_module
cli = import_module("mcp_agent.context.cli")
def test_enforce_mode_non_droppable_exit(tmp_path, monkeypatch):
    # One large must_include span that exceeds a tiny token budget
    inputs = {
        "task_targets": [],
        "changed_paths": [],
        "referenced_files": [],
        "failing_tests": [],
        "must_include": [{"uri":"file:///big.py","start":0,"end":100}],
        "never_include": [],
    }
    in_path = tmp_path / "inputs.json"
    in_path.write_text(json.dumps(inputs), encoding="utf-8")
    # Enable enforcement via settings env
    monkeypatch.setenv("MCP_CONTEXT_ENFORCE_NON_DROPPABLE", "true")
    # Budget so low that the must_include cannot fit
    code = cli.main(["assemble", "--inputs", str(in_path), "--token-budget", "1", "--neighbor-radius", "0", "--dry-run"])
    assert code == 2
