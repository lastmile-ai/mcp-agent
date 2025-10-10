from pathlib import Path

from mcp_agent.implement.applier import apply_diff


def test_apply_diff_writes_files(tmp_path: Path) -> None:
    diff = "# change"
    result = apply_diff(tmp_path, diff, ["src/foo.py", "src/bar.py"])

    written = sorted(path.relative_to(tmp_path).as_posix() for path in result.written_files)
    assert written == ["src/bar.py", "src/foo.py"]

    for rel in written:
        assert (tmp_path / rel).read_text() == diff
