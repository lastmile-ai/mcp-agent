import inspect

import pytest
from langchain_core.tools import StructuredTool
from mcp.server.fastmcp.tools import Tool as FastTool
from pydantic import BaseModel

from mcp_agent.tools.langchain_tool import from_langchain_tool


class LookupInput(BaseModel):
    query: str


def lookup_with_forward_annotation(value: "LookupInput") -> str:
    """Look up a typed query."""
    return value.query


def test_structured_conversion_preserves_original_function_metadata():
    def multiply(value: int, scale: int = 2) -> int:
        """Multiply a value by a scale."""
        return value * scale

    tool = StructuredTool.from_function(func=multiply)
    converted = from_langchain_tool(tool, name="double", description="Double a value.")

    assert multiply.__name__ == "multiply"
    assert multiply.__doc__ == "Multiply a value by a scale."
    assert tool.func is multiply
    assert converted.__name__ == "double"
    assert converted.__doc__ == "Double a value."
    assert inspect.signature(converted) == inspect.signature(multiply)
    assert converted(3) == 6
    assert converted(value=3, scale=4) == 12


def test_structured_conversions_have_independent_mcp_metadata():
    def lookup(query: str) -> str:
        """Look up a query."""
        return query

    tool = StructuredTool.from_function(func=lookup)
    first = from_langchain_tool(tool, name="first_lookup", description="First lookup.")
    second = from_langchain_tool(
        tool, name="second_lookup", description="Second lookup."
    )

    first_tool = FastTool.from_function(first)
    second_tool = FastTool.from_function(second)
    assert first_tool.name == "first_lookup"
    assert first_tool.description == "First lookup."
    assert second_tool.name == "second_lookup"
    assert second_tool.description == "Second lookup."
    assert first_tool.parameters["properties"]["query"]["type"] == "string"
    assert second_tool.parameters["properties"] == first_tool.parameters["properties"]
    assert second_tool.parameters["required"] == first_tool.parameters["required"]
    assert first("first") == "first"
    assert second("second") == "second"


@pytest.mark.asyncio
async def test_structured_conversion_preserves_async_function_behavior():
    async def lookup(query: str) -> str:
        """Look up a query asynchronously."""
        return query

    tool = StructuredTool.from_function(func=lookup)
    converted = from_langchain_tool(tool, name="async_lookup")

    assert inspect.iscoroutinefunction(converted)
    assert inspect.signature(converted) == inspect.signature(lookup)
    assert await converted("example") == "example"


def test_structured_conversion_preserves_forward_annotation_namespace():
    tool = StructuredTool.from_function(func=lookup_with_forward_annotation)
    converted = from_langchain_tool(tool, name="typed_lookup")

    fast_tool = FastTool.from_function(converted)
    assert fast_tool.parameters["properties"]["value"]["$ref"] == "#/$defs/LookupInput"
    assert converted(LookupInput(query="example")) == "example"
