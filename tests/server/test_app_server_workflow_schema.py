import pytest
from types import SimpleNamespace

from mcp_agent.app import MCPApp
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.server.app_server import create_workflow_tools


class _ToolRecorder:
    def __init__(self):
        self.decorated = []

    def tool(self, *args, **kwargs):
        name = kwargs.get("name", args[0] if args else None)

        def _decorator(func):
            self.decorated.append((name, func, kwargs))
            return func

        return _decorator


@pytest.mark.asyncio
async def test_workflow_run_schema_strips_self_and_uses_param_annotations():
    app = MCPApp(name="schema_app")
    await app.initialize()

    @app.workflow
    class MyWF(Workflow[str]):
        """Doc for MyWF"""

        @app.workflow_run
        async def run(self, q: int, flag: bool = False) -> WorkflowResult[str]:
            return WorkflowResult(value=f"{q}:{flag}")

    mcp = _ToolRecorder()
    server_context = SimpleNamespace(workflows=app.workflows, context=app.context)

    # This should create per-workflow tools; run tool must be built from run signature
    create_workflow_tools(mcp, server_context)

    # Find the "workflows-MyWF-run" tool and inspect its parameters schema via FastMCP
    names = [name for name, *_ in mcp.decorated]
    assert "workflows-MyWF-run" in names

    # We can’t call FastTool.from_function here since the tool is already created inside create_workflow_tools,
    # but we can at least ensure that the schema text embedded in the description JSON includes our parameters (q, flag)
    # Description contains a pretty-printed JSON of parameters; locate and parse it
    run_entry = next(
        (entry for entry in mcp.decorated if entry[0] == "workflows-MyWF-run"), None
    )
    assert run_entry is not None
    _, _, kwargs = run_entry
    desc = kwargs.get("description", "")
    # The description embeds the JSON schema; assert basic fields are referenced
    assert "q" in desc
    assert "flag" in desc
    assert "self" not in desc
