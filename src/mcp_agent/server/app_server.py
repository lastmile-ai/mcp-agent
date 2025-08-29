"""
MCPAgentServer - Exposes MCPApp as MCP server, and
mcp-agent workflows and agents as MCP tools.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set, Tuple, Type, TYPE_CHECKING

from mcp.server.fastmcp import Context as MCPContext, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool as FastTool

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.executor.workflow import Workflow
from mcp_agent.executor.workflow_registry import (
    WorkflowRegistry,
    InMemoryWorkflowRegistry,
)
from mcp_agent.logging.logger import get_logger
from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.mcp.mcp_server_registry import ServerRegistry

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class ServerContext(ContextDependent):
    """Context object for the MCP App server."""

    def __init__(self, mcp: FastMCP, context: "Context", **kwargs):
        super().__init__(context=context, **kwargs)
        self.mcp = mcp
        self.active_agents: Dict[str, Agent] = {}

        # Maintain a list of registered workflow tools to avoid re-registration
        # when server context is recreated for the same FastMCP instance (e.g. during
        # FastMCP sse request handling)
        if not hasattr(self.mcp, "_registered_workflow_tools"):
            setattr(self.mcp, "_registered_workflow_tools", set())

        # Initialize workflow registry if not already present
        if not self.context.workflow_registry:
            if self.context.config.execution_engine == "asyncio":
                self.context.workflow_registry = InMemoryWorkflowRegistry()
            elif self.context.config.execution_engine == "temporal":
                from mcp_agent.executor.temporal.workflow_registry import (
                    TemporalWorkflowRegistry,
                )

                self.context.workflow_registry = TemporalWorkflowRegistry(
                    executor=self.context.executor
                )
            else:
                raise ValueError(
                    f"Unsupported execution engine: {self.context.config.execution_engine}"
                )

        # TODO: saqadri (MAC) - Do we need to notify the client that tools list changed?
        # Since this is at initialization time, we may not need to
        # (depends on when the server reports that it's intialized/ready)

    def register_workflow(self, workflow_name: str, workflow_cls: Type[Workflow]):
        """Register a workflow class."""
        if workflow_name not in self.context.workflows:
            self.workflows[workflow_name] = workflow_cls
            # Create tools for this workflow if not already registered
            registered_workflow_tools = _get_registered_workflow_tools(self.mcp)
            if workflow_name not in registered_workflow_tools:
                create_workflow_specific_tools(self.mcp, workflow_name, workflow_cls)
                registered_workflow_tools.add(workflow_name)

    @property
    def app(self) -> MCPApp:
        """Get the MCPApp instance associated with this server context."""
        return self.context.app

    @property
    def workflows(self) -> Dict[str, Type[Workflow]]:
        """Get the workflows registered in this server context."""
        return self.app.workflows

    @property
    def workflow_registry(self) -> WorkflowRegistry:
        """Get the workflow registry for this server context."""
        return self.context.workflow_registry


def _get_attached_app(mcp: FastMCP) -> MCPApp | None:
    """Return the MCPApp instance attached to the FastMCP server, if any."""
    return getattr(mcp, "_mcp_agent_app", None)


def _get_registered_workflow_tools(mcp: FastMCP) -> Set[str]:
    """Return the set of registered workflow tools for the FastMCP server, if any."""
    return getattr(mcp, "_registered_workflow_tools", set())


def _get_attached_server_context(mcp: FastMCP) -> ServerContext | None:
    """Return the ServerContext attached to the FastMCP server, if any."""
    return getattr(mcp, "_mcp_agent_server_context", None)


def _resolve_workflows_and_context(
    ctx: MCPContext,
) -> Tuple[Dict[str, Type["Workflow"]] | None, Optional["Context"]]:
    """Resolve the workflows mapping and underlying app context regardless of startup mode.

    Tries lifespan ServerContext first (including compatible mocks), then attached app.
    """
    # Try lifespan-provided ServerContext first
    lifespan_ctx = getattr(ctx.request_context, "lifespan_context", None)
    if (
        lifespan_ctx is not None
        and hasattr(lifespan_ctx, "workflows")
        and hasattr(lifespan_ctx, "context")
    ):
        return lifespan_ctx.workflows, lifespan_ctx.context

    # Fall back to app attached to FastMCP
    app: MCPApp | None = _get_attached_app(ctx.fastmcp)
    if app is not None:
        return app.workflows, app.context

    return None, None


def _resolve_workflow_registry(ctx: MCPContext) -> WorkflowRegistry | None:
    """Resolve the workflow registry regardless of startup mode."""
    lifespan_ctx = getattr(ctx.request_context, "lifespan_context", None)
    # Prefer the underlying app context's registry if available
    if lifespan_ctx is not None and hasattr(lifespan_ctx, "context"):
        ctx_inner = getattr(lifespan_ctx, "context", None)
        if ctx_inner is not None and hasattr(ctx_inner, "workflow_registry"):
            return ctx_inner.workflow_registry
    # Fallback: top-level lifespan registry if present
    if lifespan_ctx is not None and hasattr(lifespan_ctx, "workflow_registry"):
        return lifespan_ctx.workflow_registry

    app: MCPApp | None = _get_attached_app(ctx.fastmcp)
    if app is not None and app.context is not None:
        return app.context.workflow_registry

    return None


def _get_param_source_function_from_workflow(workflow_cls: Type["Workflow"]):
    """Return the function to use for parameter schema for a workflow's run.

    For auto-generated workflows from @app.tool/@app.async_tool, prefer the original
    function that defined the parameters if available; fall back to the class run.
    """
    return getattr(workflow_cls, "__mcp_agent_param_source_fn__", None) or getattr(
        workflow_cls, "run"
    )


def _build_run_param_tool(workflow_cls: Type["Workflow"]) -> FastTool:
    """Return a FastTool built from the proper parameter source, skipping 'self'."""
    param_source = _get_param_source_function_from_workflow(workflow_cls)
    import inspect as _inspect

    if param_source is getattr(workflow_cls, "run"):

        def _schema_fn_proxy(*args, **kwargs):
            return None

        sig = _inspect.signature(param_source)
        params = list(sig.parameters.values())
        if params and params[0].name == "self":
            params = params[1:]
        _schema_fn_proxy.__annotations__ = dict(
            getattr(param_source, "__annotations__", {})
        )
        if "self" in _schema_fn_proxy.__annotations__:
            _schema_fn_proxy.__annotations__.pop("self", None)
        _schema_fn_proxy.__signature__ = _inspect.Signature(
            parameters=params, return_annotation=sig.return_annotation
        )
        return FastTool.from_function(_schema_fn_proxy)
    return FastTool.from_function(param_source)


def create_mcp_server_for_app(app: MCPApp, **kwargs: Any) -> FastMCP:
    """
    Create an MCP server for a given MCPApp instance.

    Args:
        app: The MCPApp instance to create a server for
        kwargs: Optional FastMCP settings to configure the server.

    Returns:
        A configured FastMCP server instance
    """

    # Create a lifespan function specific to this app
    @asynccontextmanager
    async def app_specific_lifespan(mcp: FastMCP) -> AsyncIterator[ServerContext]:
        """Initialize and manage MCPApp lifecycle."""
        # Initialize the app if it's not already initialized
        await app.initialize()

        # Create the server context which is available during the lifespan of the server
        server_context = ServerContext(mcp=mcp, context=app.context)

        # Register initial workflow tools when running with our managed lifespan
        create_workflow_tools(mcp, server_context)
        # Register function-declared tools (from @app.tool/@app.async_tool)
        create_declared_function_tools(mcp, server_context)

        try:
            yield server_context
        finally:
            # Don't clean up the MCPApp here - let the caller handle that
            pass

    # Create or attach FastMCP server
    if app.mcp:
        # Using an externally provided FastMCP instance: attach app and context
        mcp = app.mcp
        setattr(mcp, "_mcp_agent_app", app)

        # Create and attach a ServerContext since we don't control the server's lifespan
        # This enables tools to access context via ctx.fastmcp._mcp_agent_server_context
        if not hasattr(mcp, "_mcp_agent_server_context"):
            server_context = ServerContext(mcp=mcp, context=app.context)
            setattr(mcp, "_mcp_agent_server_context", server_context)
        else:
            server_context = getattr(mcp, "_mcp_agent_server_context")

        # Register per-workflow tools
        create_workflow_tools(mcp, server_context)
        # Register function-declared tools (from @app.tool/@app.async_tool)
        create_declared_function_tools(mcp, server_context)
    else:
        mcp = FastMCP(
            name=app.name or "mcp_agent_server",
            # TODO: saqadri (MAC) - create a much more detailed description
            # based on all the available agents and workflows,
            # or use the MCPApp's description if available.
            instructions=f"MCP server exposing {app.name} workflows and agents. Description: {app.description}",
            lifespan=app_specific_lifespan,
            **kwargs,
        )
        # Store the server on the app so it's discoverable and can be extended further
        app.mcp = mcp
        setattr(mcp, "_mcp_agent_app", app)

    # Register logging/setLevel handler so client can adjust verbosity dynamically
    # This enables MCP logging capability in InitializeResult.capabilities.logging
    lowlevel_server = getattr(mcp, "_mcp_server", None)
    try:
        if lowlevel_server is not None:

            @lowlevel_server.set_logging_level()
            async def _set_level(
                level: str,
            ) -> None:  # mcp.types.LoggingLevel is a Literal[str]
                try:
                    LoggingConfig.set_min_level(level)
                except Exception:
                    # Best-effort, do not crash server on invalid level
                    pass
    except Exception:
        # If handler registration fails, continue without dynamic level updates
        pass

    # region Workflow Tools

    @mcp.tool(name="workflows-list")
    def list_workflows(ctx: MCPContext) -> Dict[str, Dict[str, Any]]:
        """
        List all available workflow types with their detailed information.
        Returns information about each workflow type including name, description, and parameters.
        This helps in making an informed decision about which workflow to run.
        """
        result: Dict[str, Dict[str, Any]] = {}
        workflows, _ = _resolve_workflows_and_context(ctx)
        workflows = workflows or {}
        for workflow_name, workflow_cls in workflows.items():
            # Get workflow documentation
            run_fn_tool = FastTool.from_function(workflow_cls.run)

            # Define common endpoints for all workflows
            endpoints = [
                f"workflows-{workflow_name}-run",
                f"workflows-{workflow_name}-get_status",
            ]

            result[workflow_name] = {
                "name": workflow_name,
                "description": workflow_cls.__doc__ or run_fn_tool.description,
                "capabilities": ["run", "resume", "cancel", "get_status"],
                "tool_endpoints": endpoints,
                "run_parameters": run_fn_tool.parameters,
            }

        return result

    @mcp.tool(name="workflows-runs-list")
    async def list_workflow_runs(ctx: MCPContext) -> List[Dict[str, Any]]:
        """
        List all workflow instances (runs) with their detailed status information.

        This returns information about actual workflow instances (runs), not workflow types.
        For each running workflow, returns its ID, name, current state, and available operations.
        This helps in identifying and managing active workflow instances.

        Returns:
            A dictionary mapping workflow instance IDs to their detailed status information.
        """
        server_context = getattr(
            ctx.request_context, "lifespan_context", None
        ) or _get_attached_server_context(ctx.fastmcp)
        if server_context is None or not hasattr(server_context, "workflow_registry"):
            raise ToolError("Server context not available for MCPApp Server.")

        # Get all workflow statuses from the registry
        workflow_statuses = (
            await server_context.workflow_registry.list_workflow_statuses()
        )
        return workflow_statuses

    @mcp.tool(name="workflows-run")
    async def run_workflow(
        ctx: MCPContext,
        workflow_name: str,
        run_parameters: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Dict[str, str]:
        """
        Run a workflow with the given name.

        Args:
            workflow_name: The name of the workflow to run.
            run_parameters: Arguments to pass to the workflow run.
                workflows/list method will return the run_parameters schema for each workflow.
            kwargs: Ignore, for internal use only.

        Returns:
            A dict with workflow_id and run_id for the started workflow run, can be passed to
            workflows/get_status, workflows/resume, and workflows/cancel.
        """
        return await _workflow_run(ctx, workflow_name, run_parameters, **kwargs)

    @mcp.tool(name="workflows-get_status")
    async def get_workflow_status(
        ctx: MCPContext, workflow_name: str, run_id: str
    ) -> Dict[str, Any]:
        """
        Get the status of a running workflow.

        Provides detailed information about a workflow instance including its current state,
        whether it's running or completed, and any results or errors encountered.

        Args:
            workflow_name: The name of the workflow to check.
            run_id: The ID of the workflow instance to check,
                received from workflows/run or workflows/runs/list.

        Returns:
            A dictionary with comprehensive information about the workflow status.
        """
        return await _workflow_status(ctx, run_id, workflow_name)

    @mcp.tool(name="workflows-resume")
    async def resume_workflow(
        ctx: MCPContext,
        run_id: str,
        workflow_name: str | None = None,
        signal_name: str | None = "resume",
        payload: str | None = None,
    ) -> bool:
        """
        Resume a paused workflow.

        Args:
            run_id: The ID of the workflow to resume,
                received from workflows/run or workflows/runs/list.
            workflow_name: The name of the workflow to resume.
            signal_name: Optional name of the signal to send to resume the workflow.
                This will default to "resume", but can be a custom signal name
                if the workflow was paused on a specific signal.
            payload: Optional payload to provide the workflow upon resumption.
                For example, if a workflow is waiting for human input,
                this can be the human input.

        Returns:
            True if the workflow was resumed, False otherwise.
        """
        server_context: ServerContext = ctx.request_context.lifespan_context
        workflow_registry = server_context.workflow_registry

        if not workflow_registry:
            raise ToolError("Workflow registry not found for MCPApp Server.")

        logger.info(
            f"Resuming workflow {workflow_name} with ID {run_id} with signal '{signal_name}' and payload '{payload}'"
        )

        # Get the workflow instance from the registry
        result = await workflow_registry.resume_workflow(
            run_id=run_id,
            workflow_id=workflow_name,
            signal_name=signal_name,
            payload=payload,
        )

        if result:
            logger.debug(
                f"Signaled workflow {workflow_name} with ID {run_id} with signal '{signal_name}' and payload '{payload}'"
            )
        else:
            logger.error(
                f"Failed to signal workflow {workflow_name} with ID {run_id} with signal '{signal_name}' and payload '{payload}'"
            )

    @mcp.tool(name="workflows-cancel")
    async def cancel_workflow(
        ctx: MCPContext, run_id: str, workflow_name: str | None = None
    ) -> bool:
        """
        Cancel a running workflow.

        Args:
            run_id: The ID of the workflow instance to cancel,
                received from workflows/run or workflows/runs/list.
            workflow_name: The name of the workflow to cancel.

        Returns:
            True if the workflow was cancelled, False otherwise.
        """
        server_context: ServerContext = ctx.request_context.lifespan_context
        workflow_registry = server_context.workflow_registry

        logger.info(f"Cancelling workflow {workflow_name} with ID {run_id}")

        # Get the workflow instance from the registry
        result = await workflow_registry.cancel_workflow(
            run_id=run_id, workflow_id=workflow_name
        )

        if result:
            logger.debug(f"Cancelled workflow {workflow_name} with ID {run_id}")
        else:
            logger.error(f"Failed to cancel workflow {workflow_name} with ID {run_id}")

    # endregion

    return mcp


# region per-Workflow Tools


def create_workflow_tools(mcp: FastMCP, server_context: ServerContext):
    """
    Create workflow-specific tools for registered workflows.
    This is called at server start to register specific endpoints for each workflow.
    """
    if not server_context:
        logger.warning("Server config not available for creating workflow tools")
        return

    registered_workflow_tools = _get_registered_workflow_tools(mcp)

    for workflow_name, workflow_cls in server_context.workflows.items():
        # Skip creating generic workflows-* tools for sync/async auto tools
        if getattr(workflow_cls, "__mcp_agent_sync_tool__", False):
            continue
        if getattr(workflow_cls, "__mcp_agent_async_tool__", False):
            continue
        if workflow_name not in registered_workflow_tools:
            create_workflow_specific_tools(mcp, workflow_name, workflow_cls)
            registered_workflow_tools.add(workflow_name)

    setattr(mcp, "_registered_workflow_tools", registered_workflow_tools)


def _get_registered_function_tools(mcp: FastMCP) -> Set[str]:
    return getattr(mcp, "_registered_function_tools", set())


def _set_registered_function_tools(mcp: FastMCP, tools: Set[str]):
    setattr(mcp, "_registered_function_tools", tools)


def create_declared_function_tools(mcp: FastMCP, server_context: ServerContext):
    """
    Register tools declared via @app.tool/@app.async_tool on the attached app.
    - @app.tool registers a synchronous tool with the same signature as the function
      that runs the auto-generated workflow and waits for completion.
    - @app.async_tool registers alias tools <name>-run and <name>-get_status
      that proxy to the workflow run/status utilities.
    """
    app = _get_attached_app(mcp)
    if app is None:
        # Fallbacks for tests or externally provided contexts
        app = getattr(server_context, "app", None)
        if app is None:
            ctx = getattr(server_context, "context", None)
            if ctx is not None:
                app = getattr(ctx, "app", None)
    if app is None:
        return

    declared = getattr(app, "_declared_tools", []) or []
    if not declared:
        return

    registered = _get_registered_function_tools(mcp)

    # Utility: build a wrapper function with the same signature and return annotation
    import inspect
    import asyncio

    async def _wait_for_completion(
        ctx: MCPContext, run_id: str, timeout: float | None = None
    ):
        registry = _resolve_workflow_registry(ctx)
        if not registry:
            raise ToolError("Workflow registry not found for MCPApp Server.")
        # Try to get the workflow and wait on its task if available
        start = asyncio.get_event_loop().time()
        # Ensure the workflow is registered locally to retrieve the task
        try:
            wf = await registry.get_workflow(run_id)
            if wf is None and hasattr(registry, "register"):
                # Best-effort: some registries need explicit register; try to find by status
                # and skip if unavailable. This is a no-op for InMemory which registers at run_async.
                pass
        except Exception:
            pass
        while True:
            wf = await registry.get_workflow(run_id)
            if wf is not None:
                task = getattr(wf, "_run_task", None)
                if isinstance(task, asyncio.Task):
                    return await asyncio.wait_for(task, timeout=timeout)
                # Fallback to polling the status
                status = await wf.get_status()
                if status.get("completed"):
                    return status.get("result")
            if (
                timeout is not None
                and (asyncio.get_event_loop().time() - start) > timeout
            ):
                raise ToolError("Timed out waiting for workflow completion")
            await asyncio.sleep(0.1)

    for decl in declared:
        name = decl["name"]
        if name in registered:
            continue
        mode = decl["mode"]
        workflow_name = decl["workflow_name"]
        fn = decl.get("source_fn")
        description = decl.get("description")
        structured_output = decl.get("structured_output")

        if mode == "sync" and fn is not None:
            sig = inspect.signature(fn)
            return_ann = sig.return_annotation

            async def _wrapper(**kwargs):
                # Context will be injected by FastMCP using the special annotation below
                ctx: MCPContext = kwargs.pop(
                    "__context__"
                )  # placeholder, reassigned below via signature name
                # Start workflow and wait for completion
                result_ids = await _workflow_run(ctx, workflow_name, kwargs)
                run_id = result_ids["run_id"]
                result = await _wait_for_completion(ctx, run_id)
                # Unwrap WorkflowResult to match the original function's return type
                try:
                    from mcp_agent.executor.workflow import WorkflowResult as _WFRes
                except Exception:
                    _WFRes = None  # type: ignore
                if _WFRes is not None and isinstance(result, _WFRes):
                    return getattr(result, "value", None)
                # If get_status returned dict/str, pass through; otherwise return model
                return result

            # Attach introspection metadata to match the original function
            ann = dict(getattr(fn, "__annotations__", {}))

            # Choose a context kwarg name unlikely to clash with user params
            ctx_param_name = "ctx"
            from mcp.server.fastmcp import Context as _Ctx

            ann[ctx_param_name] = _Ctx
            ann["return"] = getattr(fn, "__annotations__", {}).get("return", return_ann)
            _wrapper.__annotations__ = ann
            _wrapper.__name__ = name
            _wrapper.__doc__ = description or (fn.__doc__ or "")

            # Build a fake signature containing original params plus context kwarg
            params = list(sig.parameters.values())
            ctx_param = inspect.Parameter(
                ctx_param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=_Ctx,
            )
            _wrapper.__signature__ = inspect.Signature(
                parameters=params + [ctx_param], return_annotation=return_ann
            )

            # FastMCP expects the actual kwarg name for context; it detects it by annotation
            # We need to map the injected kwarg inside the wrapper body. Achieve this by
            # creating a thin adapter that renames the injected context kwarg.
            async def _adapter(**kw):
                # Receive validated args plus injected context kwarg
                if ctx_param_name not in kw:
                    raise ToolError("Context not provided")
                # Rename to the placeholder expected by _wrapper
                kw["__context__"] = kw.pop(ctx_param_name)
                return await _wrapper(**kw)

            # Copy the visible signature/annotations to adapter for correct schema
            _adapter.__annotations__ = _wrapper.__annotations__
            _adapter.__name__ = _wrapper.__name__
            _adapter.__doc__ = _wrapper.__doc__
            _adapter.__signature__ = _wrapper.__signature__

            # Register the main tool with the same signature as original
            mcp.add_tool(
                _adapter,
                name=name,
                description=description or (fn.__doc__ or ""),
                structured_output=structured_output,
            )
            registered.add(name)

            # Also register a per-run status tool: <tool-name>-get_status
            status_tool_name = f"{name}-get_status"
            if status_tool_name not in registered:

                @mcp.tool(name=status_tool_name)
                async def _sync_status(ctx: MCPContext, run_id: str) -> Dict[str, Any]:
                    return await _workflow_status(
                        ctx, run_id=run_id, workflow_name=workflow_name
                    )

                registered.add(status_tool_name)

        elif mode == "async":
            # Create named aliases for async: <name>-async-run and <name>-get_status
            run_tool_name = f"{name}-async-run"
            status_tool_name = f"{name}-get_status"

            if run_tool_name not in registered:

                @mcp.tool(name=run_tool_name)
                async def _alias_run(
                    ctx: MCPContext, run_parameters: Dict[str, Any] | None = None
                ) -> Dict[str, str]:
                    return await _workflow_run(ctx, workflow_name, run_parameters or {})

                registered.add(run_tool_name)

            if status_tool_name not in registered:

                @mcp.tool(name=status_tool_name)
                async def _alias_status(ctx: MCPContext, run_id: str) -> Dict[str, Any]:
                    return await _workflow_status(
                        ctx, run_id=run_id, workflow_name=workflow_name
                    )

                registered.add(status_tool_name)

    _set_registered_function_tools(mcp, registered)


def create_workflow_specific_tools(
    mcp: FastMCP, workflow_name: str, workflow_cls: Type["Workflow"]
):
    """Create specific tools for a given workflow."""
    param_source = _get_param_source_function_from_workflow(workflow_cls)
    # Ensure we don't include 'self' in tool schema; FastMCP will ignore Context but not 'self'
    import inspect as _inspect

    if param_source is getattr(workflow_cls, "run"):
        # Wrap to drop the first positional param (self) for schema purposes
        def _schema_fn_proxy(*args, **kwargs):
            return None

        sig = _inspect.signature(param_source)
        params = list(sig.parameters.values())
        # remove leading 'self' if present
        if params and params[0].name == "self":
            params = params[1:]
        _schema_fn_proxy.__annotations__ = dict(
            getattr(param_source, "__annotations__", {})
        )
        if "self" in _schema_fn_proxy.__annotations__:
            _schema_fn_proxy.__annotations__.pop("self", None)
        _schema_fn_proxy.__signature__ = _inspect.Signature(
            parameters=params, return_annotation=sig.return_annotation
        )
        run_fn_tool = FastTool.from_function(_schema_fn_proxy)
    else:
        run_fn_tool = FastTool.from_function(param_source)
    run_fn_tool_params = json.dumps(run_fn_tool.parameters, indent=2)

    @mcp.tool(
        name=f"workflows-{workflow_name}-run",
        description=f"""
        Run the '{workflow_name}' workflow and get a dict with workflow_id and run_id back.
        Workflow Description: {workflow_cls.__doc__}

        {run_fn_tool.description}

        Args:
            run_parameters: Dictionary of parameters for the workflow run.
            The schema for these parameters is as follows:
            {run_fn_tool_params}
        """,
    )
    async def run(
        ctx: MCPContext,
        run_parameters: Dict[str, Any] | None = None,
    ) -> Dict[str, str]:
        return await _workflow_run(ctx, workflow_name, run_parameters)

    @mcp.tool(
        name=f"workflows-{workflow_name}-get_status",
        description=f"""
        Get the status of a running {workflow_name} workflow.
        
        Args:
            run_id: The run ID of the running workflow, received from workflows/{workflow_name}/run.
        """,
    )
    async def get_status(ctx: MCPContext, run_id: str) -> Dict[str, Any]:
        return await _workflow_status(ctx, run_id=run_id, workflow_name=workflow_name)


# endregion


def _get_server_descriptions(
    server_registry: ServerRegistry | None, server_names: List[str]
) -> List:
    servers: List[dict[str, str]] = []
    if server_registry:
        for server_name in server_names:
            config = server_registry.get_server_context(server_name)
            if config:
                servers.append(
                    {
                        "name": config.name,
                        "description": config.description,
                    }
                )
            else:
                servers.append({"name": server_name})
    else:
        servers = [{"name": server_name} for server_name in server_names]

    return servers


def _get_server_descriptions_as_string(
    server_registry: ServerRegistry | None, server_names: List[str]
) -> str:
    servers = _get_server_descriptions(server_registry, server_names)

    # Format each server's information as a string
    server_strings = []
    for server in servers:
        if "description" in server:
            server_strings.append(f"{server['name']}: {server['description']}")
        else:
            server_strings.append(f"{server['name']}")

    # Join all server strings with a newline
    return "\n".join(server_strings)


# region Workflow Utils


async def _workflow_run(
    ctx: MCPContext,
    workflow_name: str,
    run_parameters: Dict[str, Any] | None = None,
    **kwargs: Any,
) -> Dict[str, str]:
    # Resolve workflows and app context irrespective of startup mode
    workflows_dict, app_context = _resolve_workflows_and_context(ctx)
    if not workflows_dict or not app_context:
        raise ToolError("Server context not available for MCPApp Server.")

    if workflow_name not in workflows_dict:
        raise ToolError(f"Workflow '{workflow_name}' not found.")

    # Get the workflow class
    workflow_cls = workflows_dict[workflow_name]

    # Create and initialize the workflow instance using the factory method
    try:
        # Create workflow instance
        workflow = await workflow_cls.create(name=workflow_name, context=app_context)

        run_parameters = run_parameters or {}

        # Pass workflow_id and task_queue as special system parameters
        workflow_id = kwargs.get("workflow_id", None)
        task_queue = kwargs.get("task_queue", None)

        # Using __mcp_agent_ prefix to avoid conflicts with user parameters
        if workflow_id:
            run_parameters["__mcp_agent_workflow_id"] = workflow_id
        if task_queue:
            run_parameters["__mcp_agent_task_queue"] = task_queue

        # Run the workflow asynchronously and get its ID
        execution = await workflow.run_async(**run_parameters)

        logger.info(
            f"Workflow {workflow_name} started with workflow ID {execution.workflow_id} and run ID {execution.run_id}. Parameters: {run_parameters}"
        )

        return {
            "workflow_id": execution.workflow_id,
            "run_id": execution.run_id,
        }

    except Exception as e:
        logger.error(f"Error creating workflow {workflow_name}: {str(e)}")
        raise ToolError(f"Error creating workflow {workflow_name}: {str(e)}") from e


async def _workflow_status(
    ctx: MCPContext, run_id: str, workflow_name: str | None = None
) -> Dict[str, Any]:
    workflow_registry: WorkflowRegistry | None = _resolve_workflow_registry(ctx)

    if not workflow_registry:
        raise ToolError("Workflow registry not found for MCPApp Server.")

    workflow = await workflow_registry.get_workflow(run_id)
    workflow_id = workflow.id if workflow and workflow.id else workflow_name

    status = await workflow_registry.get_workflow_status(
        run_id=run_id, workflow_id=workflow_id
    )

    return status


# endregion
