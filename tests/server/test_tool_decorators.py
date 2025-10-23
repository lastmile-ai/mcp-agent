import asyncio
from typing import Any

import pytest

from mcp_agent.app import MCPApp, phetch
from mcp_agent.core.context import Context
from mcp.types import ToolAnnotations, Icon
from mcp.server.fastmcp import Context as FastMCPContext
from mcp_agent.server.app_server import (
    create_workflow_tools,
    create_declared_function_tools,
    _workflow_run,
)


class _ToolRecorder:
    """Helper to record tools registered via FastMCP-like interface."""

    def __init__(self):
        self.decorated_tools = []  # via mcp.tool decorator (workflow endpoints)
        self.added_tools = []  # via mcp.add_tool (sync @app.tool)

    def tool(self, *args, **kwargs):
        name = kwargs.get("name", args[0] if args else None)

        def _decorator(func):
            self.decorated_tools.append((name, func))
            return func

        return _decorator

    def add_tool(
        self,
        fn,
        *,
        name=None,
        title=None,
        description=None,
        annotations=None,
        structured_output=None,
        meta=None,
        icons=None,
        **kwargs,
    ):
        entry = {
            "name": name,
            "fn": fn,
            "title": title,
            "description": description,
            "annotations": annotations,
            "structured_output": structured_output,
            "meta": meta,
            "icons": icons,
        }
        entry.update(kwargs)
        self.added_tools.append(entry)
        return fn


def _make_ctx(server_context):
    # Minimal fake MCPContext with request_context.lifespan_context
    from types import SimpleNamespace

    ctx = SimpleNamespace()
    # Ensure a workflow registry is available for status waits
    if not hasattr(server_context, "workflow_registry"):
        from mcp_agent.executor.workflow_registry import InMemoryWorkflowRegistry

        server_context.workflow_registry = InMemoryWorkflowRegistry()

    req = SimpleNamespace(lifespan_context=server_context)
    ctx.request_context = req
    ctx.fastmcp = SimpleNamespace(_mcp_agent_app=None)
    return ctx


@pytest.mark.asyncio
async def test_app_tool_registers_and_executes_sync_tool():
    app = MCPApp(name="test_app_tool")
    await app.initialize()

    @app.tool(
        name="echo",
        title="Echo Title",
        description="Echo input",
        annotations={"idempotentHint": True},
        icons=[{"src": "emoji:wave"}],
        meta={"source": "test"},
        structured_output=True,
    )
    async def echo(text: str) -> str:
        return text + "!"

    # Prepare mock FastMCP and server context
    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    # Register generated per-workflow tools and function-declared tools
    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    # Verify tool names: only the sync tool endpoint is added
    _decorated_names = {name for name, _ in mcp.decorated_tools}
    added_names = {entry["name"] for entry in mcp.added_tools}

    # No workflows-* aliases for sync tools; check only echo
    assert "echo" in added_names  # synchronous tool

    # Execute the synchronous tool function and ensure it returns unwrapped value
    # Find the registered sync tool function
    sync_tool_entry = next(
        entry for entry in mcp.added_tools if entry["name"] == "echo"
    )
    sync_tool_fn = sync_tool_entry["fn"]
    ctx = _make_ctx(server_context)
    result = await sync_tool_fn(text="hi", ctx=ctx)
    assert result == "hi!"  # unwrapped (not WorkflowResult)
    bound_app_ctx = getattr(ctx, "bound_app_context", None)
    assert bound_app_ctx is not None
    assert bound_app_ctx is not server_context.context
    assert bound_app_ctx.fastmcp == ctx.fastmcp
    assert sync_tool_entry["title"] == "Echo Title"
    assert isinstance(sync_tool_entry["annotations"], ToolAnnotations)
    assert sync_tool_entry["annotations"].idempotentHint is True
    assert sync_tool_entry["icons"] == [Icon(src="emoji:wave")]
    # meta support in FastMCP add_tool pending upstream release; expect None for now
    assert sync_tool_entry.get("meta") in ({"source": "test"}, None)
    assert sync_tool_entry["structured_output"] is True

    # Also ensure the underlying workflow returned a WorkflowResult
    # Start via workflow_run to get run_id, then wait for completion and inspect
    run_info = await _workflow_run(ctx, "echo", {"text": "ok"})
    run_id = run_info["run_id"]
    # Poll status until completed (bounded wait)
    for _ in range(200):
        status = await app.context.workflow_registry.get_workflow_status(run_id)
        if status.get("completed"):
            break
        await asyncio.sleep(0.01)
    assert status.get("completed") is True
    # The recorded result is a WorkflowResult model dump; check value field
    result_payload = status.get("result")
    if isinstance(result_payload, dict) and "value" in result_payload:
        assert result_payload["value"] == "ok!"
    else:
        assert result_payload in ("ok!", {"result": "ok!"})


@pytest.mark.asyncio
async def test_app_async_tool_registers_aliases_and_workflow_tools():
    app = MCPApp(name="test_app_async_tool")
    await app.initialize()

    @app.async_tool(
        name="long",
        title="Long Task",
        annotations={"readOnlyHint": True},
        icons=[Icon(src="emoji:check")],
        meta={"async": True},
        structured_output=None,
    )
    async def long_task(x: int) -> str:
        return f"done:{x}"

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    decorated_names = {name for name, _ in mcp.decorated_tools}
    added_names = {entry["name"] for entry in mcp.added_tools}

    # We register the async tool under its given name via add_tool
    assert "long" in added_names
    long_entry = next(entry for entry in mcp.added_tools if entry["name"] == "long")
    assert long_entry["title"] == "Long Task"
    assert isinstance(long_entry["annotations"], ToolAnnotations)
    assert long_entry["annotations"].readOnlyHint is True
    assert long_entry["icons"] == [Icon(src="emoji:check")]
    assert long_entry.get("meta") in ({"async": True}, None)
    # And we suppress workflows-* for async auto tools
    assert "workflows-long-run" not in decorated_names


@pytest.mark.asyncio
async def test_async_tool_wrappers_capture_workflow_name(monkeypatch):
    app = MCPApp(name="test_async_tool_closure")
    await app.initialize()

    @app.async_tool(name="first")
    async def first_task(value: str) -> str:
        return f"first:{value}"

    @app.async_tool(name="second")
    async def second_task(value: str) -> str:
        return f"second:{value}"

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    calls: list[tuple[str, Any]] = []

    async def _fake_workflow_run(ctx, workflow_name, run_parameters=None, **kwargs):
        calls.append((workflow_name, run_parameters))
        return {"workflow_id": workflow_name, "run_id": f"run-{workflow_name}"}

    monkeypatch.setattr("mcp_agent.server.app_server._workflow_run", _fake_workflow_run)

    ctx = _make_ctx(server_context)
    first_entry = next(entry for entry in mcp.added_tools if entry["name"] == "first")
    second_entry = next(entry for entry in mcp.added_tools if entry["name"] == "second")

    await first_entry["fn"](value="one", ctx=ctx)
    await second_entry["fn"](value="two", ctx=ctx)

    assert calls == [
        ("first", {"value": "one"}),
        ("second", {"value": "two"}),
    ]


@pytest.mark.asyncio
async def test_sync_tool_wrappers_capture_workflow_name(monkeypatch):
    app = MCPApp(name="test_sync_tool_closure")
    await app.initialize()

    @app.tool(name="alpha")
    async def alpha_task(x: int) -> str:
        return f"alpha:{x}"

    @app.tool(name="beta")
    async def beta_task(x: int) -> str:
        return f"beta:{x}"

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    run_calls: list[tuple[str, Any]] = []
    from mcp_agent.server import app_server as _app_server

    original_workflow_run = _app_server._workflow_run

    async def _fake_workflow_run(ctx, workflow_name, run_parameters=None, **kwargs):
        run_calls.append((workflow_name, run_parameters))
        return await original_workflow_run(ctx, workflow_name, run_parameters, **kwargs)

    monkeypatch.setattr(_app_server, "_workflow_run", _fake_workflow_run)

    ctx = _make_ctx(server_context)
    alpha_entry = next(entry for entry in mcp.added_tools if entry["name"] == "alpha")
    beta_entry = next(entry for entry in mcp.added_tools if entry["name"] == "beta")

    alpha_result = await alpha_entry["fn"](x=1, ctx=ctx)
    beta_result = await beta_entry["fn"](x=2, ctx=ctx)

    assert alpha_result == "alpha:1"
    assert beta_result == "beta:2"
    assert run_calls == [
        ("alpha", {"x": 1}),
        ("beta", {"x": 2}),
    ]


@pytest.mark.asyncio
async def test_auto_workflow_wraps_plain_return_in_workflowresult():
    app = MCPApp(name="test_wrap")
    await app.initialize()

    @app.async_tool(name="wrapme")
    async def wrapme(v: int) -> int:
        # plain int, should be wrapped inside WorkflowResult internally
        return v + 1

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()
    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    ctx = _make_ctx(server_context)
    run_info = await _workflow_run(ctx, "wrapme", {"v": 41})
    run_id = run_info["run_id"]

    # Inspect workflow's task result type by polling status for completion
    for _ in range(100):
        status = await app.context.workflow_registry.get_workflow_status(run_id)
        if status.get("completed"):
            break
        await asyncio.sleep(0.01)
    assert status.get("completed") is True

    # Cross-check that the underlying run returned a WorkflowResult by re-running via registry path
    # We can't import the internal task here; assert observable effect: result equals expected and no exceptions
    assert status.get("error") in (None, "")
    # And the computed value was correct
    result_payload = status.get("result")
    if isinstance(result_payload, dict) and "value" in result_payload:
        assert result_payload["value"] == 42
    else:
        assert result_payload in (42, {"result": 42})


@pytest.mark.asyncio
async def test_workflow_run_binds_app_context_per_request():
    app = MCPApp(name="test_request_binding")
    await app.initialize()

    sentinel_session = object()
    app.context.upstream_session = sentinel_session

    captured: dict[str, Any] = {}

    @app.async_tool(name="binding_tool")
    async def binding_tool(
        value: int,
        app_ctx: Context | None = None,
        ctx: FastMCPContext | None = None,
    ) -> str:
        captured["app_ctx"] = app_ctx
        captured["ctx"] = ctx
        if app_ctx is not None:
            # Access session property to confirm fallback path works during execution
            captured["session_property"] = app_ctx.session
            captured["request_context"] = getattr(app_ctx, "_request_context", None)
            captured["fastmcp"] = app_ctx.fastmcp
        return f"done:{value}"


@pytest.mark.asyncio
async def test_tool_decorator_defaults_to_phetch_icon_when_no_icons_provided():
    """Verify that when no icons parameter is provided, the default phetch icon is used."""
    app = MCPApp(name="test_default_icon")
    await app.initialize()

    # Register a tool without specifying icons
    @app.tool(name="no_icon_tool", description="Tool without icons")
    async def no_icon_tool(text: str) -> str:
        return text

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    # Find the registered tool and check its icons
    tool_entry = next(
        (entry for entry in mcp.added_tools if entry["name"] == "no_icon_tool"), None
    )
    assert tool_entry is not None, "Tool should be registered"

    # Extract icons from the tool entry
    icons = tool_entry["icons"]
    assert icons is not None, "Icons should not be None"
    assert len(icons) == 1, "Should have exactly one icon"
    assert icons[0] == phetch, "Icon should be the default phetch icon"


@pytest.mark.asyncio
async def test_tool_decorator_uses_custom_icons_when_provided():
    """Verify that when icons parameter is provided, those icons are used instead of the default."""
    app = MCPApp(name="test_custom_icon")
    await app.initialize()

    # Create a custom icon
    custom_icon = Icon(src="data:image/png;base64,customdata")

    # Register a tool with custom icons
    @app.tool(
        name="custom_icon_tool",
        description="Tool with custom icon",
        icons=[custom_icon],
    )
    async def custom_icon_tool(text: str) -> str:
        return text

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    # Find the registered tool and check its icons
    tool_entry = next(
        (entry for entry in mcp.added_tools if entry["name"] == "custom_icon_tool"),
        None,
    )
    assert tool_entry is not None, "Tool should be registered"

    # Extract icons from the tool entry
    icons = tool_entry["icons"]
    assert icons is not None, "Icons should not be None"
    assert len(icons) == 1, "Should have exactly one icon"
    assert icons[0] == custom_icon, "Icon should be the custom icon, not phetch"
    assert icons[0] != phetch, "Icon should NOT be the default phetch icon"


@pytest.mark.asyncio
async def test_async_tool_decorator_defaults_to_phetch_icon_when_no_icons_provided():
    """Verify that @app.async_tool defaults to phetch icon when no icons are provided."""
    app = MCPApp(name="test_async_default_icon")
    await app.initialize()

    # Register an async tool without specifying icons
    @app.async_tool(name="no_icon_async_tool", description="Async tool without icons")
    async def no_icon_async_tool(text: str) -> str:
        return text

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    # Find the registered tool and check its icons
    tool_entry = next(
        (entry for entry in mcp.added_tools if entry["name"] == "no_icon_async_tool"),
        None,
    )
    assert tool_entry is not None, "Tool should be registered"

    # Extract icons from the tool entry
    icons = tool_entry["icons"]
    assert icons is not None, "Icons should not be None"
    assert len(icons) == 1, "Should have exactly one icon"
    assert icons[0] == phetch, "Icon should be the default phetch icon"


@pytest.mark.asyncio
async def test_async_tool_decorator_uses_custom_icons_when_provided():
    """Verify that @app.async_tool uses custom icons when provided."""
    app = MCPApp(name="test_async_custom_icon")
    await app.initialize()

    # Create a custom icon
    custom_icon = Icon(src="data:image/png;base64,customasyncdata")

    # Register an async tool with custom icons
    @app.async_tool(
        name="custom_icon_async_tool",
        description="Async tool with custom icon",
        icons=[custom_icon],
    )
    async def custom_icon_async_tool(text: str) -> str:
        return text

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    # Find the registered tool and check its icons
    tool_entry = next(
        (
            entry
            for entry in mcp.added_tools
            if entry["name"] == "custom_icon_async_tool"
        ),
        None,
    )
    assert tool_entry is not None, "Tool should be registered"

    # Extract icons from the tool entry
    icons = tool_entry["icons"]
    assert icons is not None, "Icons should not be None"
    assert len(icons) == 1, "Should have exactly one icon"
    assert icons[0] == custom_icon, "Icon should be the custom icon, not phetch"
    assert icons[0] != phetch, "Icon should NOT be the default phetch icon"
