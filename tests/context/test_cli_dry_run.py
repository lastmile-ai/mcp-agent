import json
from importlib import import_module

cli = import_module("mcp_agent.context.cli")


def test_cli_dry_run(tmp_path, capsys):
    inputs = {
        "task_targets": [],
        "changed_paths": ["file:///z.py"],
        "referenced_files": [],
        "failing_tests": [],
        "must_include": [],
        "never_include": [],
    }
    in_path = tmp_path / "inputs.json"
    out_path = tmp_path / "manifest.json"
    in_path.write_text(json.dumps(inputs), encoding="utf-8")
    code = cli.main(["assemble", "--inputs", str(in_path), "--out", str(out_path), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "pack_hash:" in out
    # manifest written
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "meta" in data and "pack_hash" in data["meta"]
