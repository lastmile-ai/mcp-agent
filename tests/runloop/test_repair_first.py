import pytest

from mcp_agent.implement.repairer import Repairer


@pytest.mark.asyncio
async def test_repairer_tracks_attempts_and_diff() -> None:
    repairer = Repairer()

    result1 = await repairer.run(["tests/foo::test_bar"])
    assert "tests/foo::test_bar" in result1.diff
    assert result1.attempts == 1

    result2 = await repairer.run([])
    assert result2.diff == "# repair"
    assert result2.attempts == 2
