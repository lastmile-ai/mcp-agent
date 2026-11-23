import sys
import types

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools import Tool

from mcp_agent.app import MCPApp
from mcp_agent.config import Settings
from mcp_agent.server.tool_adapter import create_tool_adapter_signature


@pytest.fixture(params=[True, False], ids=["postponed", "eager"])
def source_module(request):
    module = types.ModuleType("postponed_input_fixture")
    sys.modules[module.__name__] = module
    exec(
        ("from __future__ import annotations\n" if request.param else "")
        + "from pydantic import BaseModel\n"
        "class Payload(BaseModel):\n    code: str\n"
        "async def read_code(payload: Payload) -> str:\n    return payload.code\n",
        module.__dict__,
    )
    yield module
    sys.modules.pop(module.__name__, None)


@pytest.mark.parametrize("decorator", ["tool", "async_tool"])
def test_postponed_model_input_registers(source_module, decorator):
    fn = source_module.read_code
    expected = Tool.from_function(fn).parameters
    app = MCPApp(
        name="postponed-input",
        settings=Settings(execution_engine="asyncio"),
        mcp=FastMCP("test"),
    )
    assert getattr(app, decorator)(name="read_code")(fn) is fn
    actual = Tool.from_function(
        create_tool_adapter_signature(fn, "read_code")
    ).parameters
    assert actual == expected


@pytest.mark.asyncio
async def test_adapter_validates_model_input(source_module):
    fn = source_module.read_code
    adapter = create_tool_adapter_signature(fn, "read_code")
    tool = Tool.from_function(adapter)
    parsed = tool.fn_metadata.arg_model.model_validate({"payload": {"code": "ok"}})
    assert isinstance(parsed.payload, source_module.Payload)
    assert await fn(parsed.payload) == "ok"


@pytest.mark.parametrize("decorator", ["tool", "async_tool"])
def test_registered_server_tool_keeps_input_schema(source_module, decorator):
    from types import SimpleNamespace
    from mcp_agent.core.context import Context
    from mcp_agent.server.app_server import create_declared_function_tools

    mcp = FastMCP("wire")
    app = MCPApp(
        name="postponed", settings=Settings(execution_engine="asyncio"), mcp=mcp
    )
    getattr(app, decorator)(name="read_code")(source_module.read_code)
    context = Context()
    mcp._mcp_agent_app = app
    create_declared_function_tools(
        mcp, SimpleNamespace(context=context, workflows=app.workflows)
    )
    tool = mcp._tool_manager.get_tool("read_code")
    assert tool is not None
    assert tool.parameters["$defs"]["Payload"]["properties"]["code"]["type"] == "string"
