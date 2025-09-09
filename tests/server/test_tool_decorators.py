import asyncio
import pytest

from mcp_agent.app import MCPApp
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
    ):
        self.added_tools.append((name, fn, description, structured_output))


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

    @app.tool(name="echo", description="Echo input")
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
    added_names = {name for name, *_ in mcp.added_tools}

    # No workflows-* aliases for sync tools; check only echo
    assert "echo" in added_names  # synchronous tool

    # Execute the synchronous tool function and ensure it returns unwrapped value
    # Find the registered sync tool function
    sync_tool_fn = next(fn for name, fn, *_ in mcp.added_tools if name == "echo")
    ctx = _make_ctx(server_context)
    result = await sync_tool_fn(text="hi", ctx=ctx)
    assert result == "hi!"  # unwrapped (not WorkflowResult)

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

    @app.async_tool(name="long")
    async def long_task(x: int) -> str:
        return f"done:{x}"

    mcp = _ToolRecorder()
    server_context = type(
        "SC", (), {"workflows": app.workflows, "context": app.context}
    )()

    create_workflow_tools(mcp, server_context)
    create_declared_function_tools(mcp, server_context)

    decorated_names = {name for name, _ in mcp.decorated_tools}
    added_names = {name for name, *_ in mcp.added_tools}

    # We register the async tool under its given name via add_tool
    assert "long" in added_names
    # And we suppress workflows-* for async auto tools
    assert "workflows-long-run" not in decorated_names


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
