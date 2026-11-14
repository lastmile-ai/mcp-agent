import pytest
from mcp.types import Tool

from mcp_agent.utils.tool_filter import ToolFilter


@pytest.mark.parametrize(
    ("allowed", "expected_names"),
    [
        (None, ["filesystem_read_file", "filesystem_write_file"]),
        ([], []),
        (["read_file"], ["filesystem_read_file"]),
        (["filesystem_read_file"], ["filesystem_read_file"]),
    ],
)
def test_filter_tools_allowed_list(
    allowed: list[str] | None, expected_names: list[str]
) -> None:
    tools = [
        Tool(name="filesystem_read_file", inputSchema={"type": "object"}),
        Tool(name="filesystem_write_file", inputSchema={"type": "object"}),
    ]

    filtered = ToolFilter(allowed=allowed).filter_tools(tools)

    assert [tool.name for tool in filtered] == expected_names


def test_filter_tools_empty_allowlist_preserves_server_override() -> None:
    tools = [
        Tool(name="filesystem_read_file", inputSchema={"type": "object"}),
        Tool(name="github_search", inputSchema={"type": "object"}),
    ]
    tool_filter = ToolFilter(
        allowed=[], server_filters={"filesystem": {"allowed": ["read_file"]}}
    )

    assert [tool.name for tool in tool_filter.filter_tools(tools)] == [
        "filesystem_read_file"
    ]


def test_filter_tools_empty_allowlist_preserves_custom_override() -> None:
    tool = Tool(name="read_file", inputSchema={"type": "object"})
    tool_filter = ToolFilter(
        allowed=[], custom_filter=lambda candidate: candidate == tool
    )

    assert tool_filter.filter_tools([tool]) == [tool]
