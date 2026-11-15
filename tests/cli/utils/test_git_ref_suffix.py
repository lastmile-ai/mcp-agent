import pytest

from mcp_agent.cli.utils.git_utils import sanitize_git_ref_component


@pytest.mark.parametrize(
    "name",
    ["release.lock.", "release.lock.lock", "release.LOCK."],
)
def test_sanitize_ref_component_removes_all_invalid_suffixes(name):
    assert sanitize_git_ref_component(name) == "release"


def test_sanitize_ref_component_keeps_internal_lock():
    assert sanitize_git_ref_component("release.lock-notes") == "release.lock-notes"
