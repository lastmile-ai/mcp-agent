import pytest

from mcp_agent.checks.tests_index import expand_tests, read_index
from mcp_agent.runloop.checks import run_targeted_checks


def test_read_index_returns_entries(tmp_path) -> None:
    index = tmp_path / "index.txt"
    index.write_text("tests/module/test_one.py\n\n tests/module/test_two.py \n")

    assert read_index(index) == ["tests/module/test_one.py", "tests/module/test_two.py"]
    assert read_index(tmp_path / "missing.txt") == []


def test_expand_tests_matches_prefixes() -> None:
    changed = ["tests/module", "tests/other/test_three.py"]
    index = [
        "tests/module/test_one.py",
        "tests/module/test_two.py",
        "tests/extra/test_four.py",
    ]
    assert expand_tests(changed, index) == [
        "tests/module/test_one.py",
        "tests/module/test_two.py",
    ]


@pytest.mark.asyncio
async def test_run_targeted_checks_echoes_commands() -> None:
    commands = ["ruff src", "pytest tests"]
    results = await run_targeted_checks(commands)

    assert [r.command for r in results] == commands
    assert all(r.passed for r in results)
