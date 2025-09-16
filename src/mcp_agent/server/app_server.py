"""
MCPAgentServer - Exposes MCPApp as MCP server, and
mcp-agent workflows and agents as MCP tools.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set, Tuple, Type, TYPE_CHECKING
import os
import secrets
import asyncio

from mcp.server.fastmcp import Context as MCPContext, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool as FastTool

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.executor.workflow import Workflow
from mcp_agent.executor.workflow_registry import (
    InMemoryWorkflowRegistry,
    WorkflowRegistry,
    WorkflowRunsPage,
)

from mcp_agent.logging.logger import get_logger
from mcp_agent.logging.logger import LoggingConfig
from mcp_agent.mcp.mcp_server_registry import ServerRegistry

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)
# Simple in-memory registry mapping workflow execution_id -> upstream session handle.
# Allows external workers (e.g., Temporal) to relay logs/prompts through MCPApp.
_RUN_SESSION_REGISTRY: Dict[str, Any] = {}
_RUN_EXECUTION_ID_REGISTRY: Dict[str, str] = {}
_RUN_SESSION_LOCK = asyncio.Lock()
_PENDING_PROMPTS: Dict[str, Dict[str, Any]] = {}
_PENDING_PROMPTS_LOCK = asyncio.Lock()
_IDEMPOTENCY_KEYS_SEEN: Dict[str, Set[str]] = {}
_IDEMPOTENCY_KEYS_LOCK = asyncio.Lock()


async def _register_session(run_id: str, execution_id: str, session: Any) -> None:
    async with _RUN_SESSION_LOCK:
        _RUN_SESSION_REGISTRY[execution_id] = session
        _RUN_EXECUTION_ID_REGISTRY[run_id] = execution_id
        try:
            logger.debug(
                f"Registered upstream session for run_id={run_id}, execution_id={execution_id}, session_id={id(session)}"
            )
        except Exception:
            pass


async def _unregister_session(run_id: str) -> None:
    async with _RUN_SESSION_LOCK:
        execution_id = _RUN_EXECUTION_ID_REGISTRY.pop(run_id, None)
        if execution_id:
            _RUN_SESSION_REGISTRY.pop(execution_id, None)
            try:
                logger.debug(
                    f"Unregistered upstream session mapping for run_id={run_id}, execution_id={execution_id}"
                )
            except Exception:
                pass


async def _get_session(execution_id: str) -> Any | None:
    async with _RUN_SESSION_LOCK:
        session = _RUN_SESSION_REGISTRY.get(execution_id)
        try:
            logger.debug(
                (
                    f"Lookup session for execution_id={execution_id}: "
                    + (f"found session_id={id(session)}" if session else "not found")
                )
            )
        except Exception:
            pass
        return session


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


def _set_upstream_from_request_ctx_if_available(ctx: MCPContext) -> None:
    """Attach the low-level server session to the app context for upstream log forwarding.

    This ensures logs emitted from background workflow tasks are forwarded to the client
    even when the low-level request contextvar is not available in those tasks.
    """
    # First, try to use the session property from the FastMCP Context
    session = None
    try:
        session = (
            ctx.session
        )  # This accesses the property which returns ctx.request_context.session
    except (AttributeError, ValueError):
        # ctx.session property might raise ValueError if context not available
        pass

    if session is not None:
        app: MCPApp | None = _get_attached_app(ctx.fastmcp)
        if app is not None and getattr(app, "context", None) is not None:
            # Set on global app context so the logger can access it
            # Previously captured; no need to keep old value
            # Use direct assignment for Pydantic model
            app.context.upstream_session = session
            return
        else:
            return


def _resolve_workflows_and_context(
    ctx: MCPContext,
) -> Tuple[Dict[str, Type["Workflow"]] | None, Optional["Context"]]:
    """Resolve the workflows mapping and underlying app context regardless of startup mode.

    Tries lifespan ServerContext first (including compatible mocks), then attached app.
    Also ensures the app context is updated with the current upstream session once per request.
    """
    # Try lifespan-provided ServerContext first
    lifespan_ctx = getattr(ctx.request_context, "lifespan_context", None)
    if (
        lifespan_ctx is not None
        and hasattr(lifespan_ctx, "workflows")
        and hasattr(lifespan_ctx, "context")
    ):
        # Ensure upstream session once at resolution time
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
        return lifespan_ctx.workflows, lifespan_ctx.context

    # Fall back to app attached to FastMCP
    app: MCPApp | None = _get_attached_app(ctx.fastmcp)

    if app is not None:
        # Ensure the app context has the current request's session set so background logs forward
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
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
    """Return a FastTool for schema purposes, filtering internals like 'self', 'app_ctx', and FastMCP Context."""
    param_source = _get_param_source_function_from_workflow(workflow_cls)
    import inspect as _inspect

    def _make_filtered_schema_proxy(fn):
        def _schema_fn_proxy(*args, **kwargs):
            return None

        sig = _inspect.signature(fn)
        params = list(sig.parameters.values())

        # Drop leading 'self' if present
        if params and params[0].name == "self":
            params = params[1:]

        # Drop internal-only params: app_ctx and any FastMCP Context (ctx/context)
        try:
            from mcp.server.fastmcp import Context as _Ctx  # type: ignore
        except Exception:
            _Ctx = None  # type: ignore

        filtered_params = []
        for p in params:
            if p.name == "app_ctx":
                continue
            if p.name in ("ctx", "context"):
                continue
            ann = p.annotation
            if ann is not _inspect._empty and _Ctx is not None and ann is _Ctx:
                continue
            filtered_params.append(p)

        # Copy annotations and remove filtered keys
        ann_map = dict(getattr(fn, "__annotations__", {}))
        for k in ["self", "app_ctx", "ctx", "context"]:
            if k in ann_map:
                ann_map.pop(k, None)

        _schema_fn_proxy.__annotations__ = ann_map
        _schema_fn_proxy.__signature__ = _inspect.Signature(
            parameters=filtered_params, return_annotation=sig.return_annotation
        )
        return _schema_fn_proxy

    # If using run method, filter and drop 'self'
    if param_source is getattr(workflow_cls, "run"):
        return FastTool.from_function(_make_filtered_schema_proxy(param_source))

    # Otherwise, param_source is likely the original function from @app.tool/@app.async_tool
    # Filter out app_ctx/ctx/context from the schema
    return FastTool.from_function(_make_filtered_schema_proxy(param_source))


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

    # Helper: install internal HTTP routes (not MCP tools)
    def _install_internal_routes(mcp_server: FastMCP) -> None:
        def _get_fallback_upstream_session() -> Any | None:
            """Best-effort fallback to the most recent upstream session captured on the app context.

            This helps when a workflow run's mapping has not been refreshed after a client reconnect.
            """
            try:
                app_obj: MCPApp | None = _get_attached_app(mcp_server)
                if app_obj and getattr(app_obj, "context", None) is not None:
                    return getattr(app_obj.context, "upstream_session", None)
            except Exception:
                return None
            return None

        @mcp_server.custom_route(
            "/internal/session/by-run/{execution_id}/notify",
            methods=["POST"],
            include_in_schema=False,
        )
        async def _relay_notify(request: Request):
            body = await request.json()
            execution_id = request.path_params.get("execution_id")
            method = body.get("method")
            params = body.get("params") or {}

            # Optional shared-secret auth
            gw_token = os.environ.get("MCP_GATEWAY_TOKEN")
            if gw_token:
                bearer = request.headers.get("Authorization", "")
                bearer_token = (
                    bearer.split(" ", 1)[1]
                    if bearer.lower().startswith("bearer ")
                    else ""
                )
                header_tok = request.headers.get("X-MCP-Gateway-Token", "")
                if not (
                    secrets.compare_digest(header_tok, gw_token)
                    or secrets.compare_digest(bearer_token, gw_token)
                ):
                    return JSONResponse(
                        {"ok": False, "error": "unauthorized"}, status_code=401
                    )

            # Optional idempotency handling
            idempotency_key = params.get("idempotency_key")
            if idempotency_key:
                async with _IDEMPOTENCY_KEYS_LOCK:
                    seen = _IDEMPOTENCY_KEYS_SEEN.setdefault(execution_id or "", set())
                    if idempotency_key in seen:
                        return JSONResponse({"ok": True, "idempotent": True})
                    seen.add(idempotency_key)

            # Prefer latest upstream session first
            latest_session = _get_fallback_upstream_session()
            tried_latest = False
            if latest_session is not None:
                tried_latest = True
                try:
                    if method == "notifications/message":
                        level = str(params.get("level", "info"))
                        data = params.get("data")
                        logger_name = params.get("logger")
                        related_request_id = params.get("related_request_id")
                        await latest_session.send_log_message(  # type: ignore[attr-defined]
                            level=level,  # type: ignore[arg-type]
                            data=data,
                            logger=logger_name,
                            related_request_id=related_request_id,
                        )
                        # logger.debug(
                        #     f"[notify] delivered via latest session_id={id(latest_session)} (message)"
                        # )
                    elif method == "notifications/progress":
                        progress_token = params.get("progressToken")
                        progress = params.get("progress")
                        total = params.get("total")
                        message = params.get("message")
                        await latest_session.send_progress_notification(  # type: ignore[attr-defined]
                            progress_token=progress_token,
                            progress=progress,
                            total=total,
                            message=message,
                        )
                        # logger.debug(
                        #     f"[notify] delivered via latest session_id={id(latest_session)} (progress)"
                        # )
                    else:
                        rpc = getattr(latest_session, "rpc", None)
                        if rpc and hasattr(rpc, "notify"):
                            await rpc.notify(method, params)
                            # logger.debug(
                            #     f"[notify] delivered via latest session_id={id(latest_session)} (generic '{method}')"
                            # )
                        else:
                            return JSONResponse(
                                {"ok": False, "error": f"unsupported method: {method}"},
                                status_code=400,
                            )
                    # Successful with latest → bind mapping for consistency
                    try:
                        await _register_session(
                            run_id=execution_id,
                            execution_id=execution_id,
                            session=latest_session,
                        )
                        # logger.info(
                        #     f"[notify] rebound mapping to latest session_id={id(latest_session)} for execution_id={execution_id}"
                        # )
                    except Exception:
                        pass
                    return JSONResponse({"ok": True})
                except Exception as e_latest:
                    logger.warning(
                        f"[notify] latest session delivery failed for execution_id={execution_id}: {e_latest}"
                    )

            # Fallback to mapped session
            mapped_session = await _get_session(execution_id)
            if not mapped_session:
                logger.warning(
                    f"[notify] session_not_available for execution_id={execution_id} (tried_latest={tried_latest})"
                )
                return JSONResponse(
                    {"ok": False, "error": "session_not_available"}, status_code=503
                )

            try:
                if method == "notifications/message":
                    level = str(params.get("level", "info"))
                    data = params.get("data")
                    logger_name = params.get("logger")
                    related_request_id = params.get("related_request_id")
                    await mapped_session.send_log_message(  # type: ignore[attr-defined]
                        level=level,  # type: ignore[arg-type]
                        data=data,
                        logger=logger_name,
                        related_request_id=related_request_id,
                    )
                    # logger.debug(
                    #     f"[notify] delivered via mapped session_id={id(mapped_session)} (message)"
                    # )
                elif method == "notifications/progress":
                    progress_token = params.get("progressToken")
                    progress = params.get("progress")
                    total = params.get("total")
                    message = params.get("message")
                    await mapped_session.send_progress_notification(  # type: ignore[attr-defined]
                        progress_token=progress_token,
                        progress=progress,
                        total=total,
                        message=message,
                    )
                    # logger.debug(
                    #     f"[notify] delivered via mapped session_id={id(mapped_session)} (progress)"
                    # )
                else:
                    rpc = getattr(mapped_session, "rpc", None)
                    if rpc and hasattr(rpc, "notify"):
                        await rpc.notify(method, params)
                        # logger.debug(
                        #     f"[notify] delivered via mapped session_id={id(mapped_session)} (generic '{method}')"
                        # )
                    else:
                        return JSONResponse(
                            {"ok": False, "error": f"unsupported method: {method}"},
                            status_code=400,
                        )
                return JSONResponse({"ok": True})
            except Exception as e_mapped:
                # Best-effort for notifications
                if isinstance(method, str) and method.startswith("notifications/"):
                    # logger.warning(
                    #     f"[notify] dropped notification for execution_id={execution_id}: {e_mapped}"
                    # )
                    return JSONResponse({"ok": True, "dropped": True})
                # logger.error(
                #     f"[notify] error forwarding for execution_id={execution_id}: {e_mapped}"
                # )
                return JSONResponse(
                    {"ok": False, "error": str(e_mapped)}, status_code=500
                )

        @mcp_server.custom_route(
            "/internal/session/by-run/{execution_id}/request",
            methods=["POST"],
            include_in_schema=False,
        )
        async def _relay_request(request: Request):
            from mcp.types import (
                CreateMessageRequest,
                CreateMessageRequestParams,
                CreateMessageResult,
                ElicitRequest,
                ElicitRequestParams,
                ElicitResult,
                ListRootsRequest,
                ListRootsResult,
                PingRequest,
                EmptyResult,
                ServerRequest,
            )

            body = await request.json()
            execution_id = request.path_params.get("execution_id")
            method = body.get("method")
            params = body.get("params") or {}

            # Prefer latest upstream session first
            latest_session = _get_fallback_upstream_session()
            if latest_session is not None:
                try:
                    rpc = getattr(latest_session, "rpc", None)
                    if rpc and hasattr(rpc, "request"):
                        result = await rpc.request(method, params)
                        # logger.debug(
                        #     f"[request] delivered via latest session_id={id(latest_session)} (generic '{method}')"
                        # )
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                            )
                            logger.debug(
                                f"[request] rebound mapping to latest session_id={id(latest_session)} for execution_id={execution_id}"
                            )
                        except Exception:
                            pass
                        return JSONResponse(result)
                    # If latest_session lacks rpc.request, try a limited mapping path
                    if method == "sampling/createMessage":
                        req = ServerRequest(
                            CreateMessageRequest(
                                method="sampling/createMessage",
                                params=CreateMessageRequestParams(**params),
                            )
                        )
                        result = await latest_session.send_request(  # type: ignore[attr-defined]
                            request=req,
                            result_type=CreateMessageResult,
                        )
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                            )
                        except Exception:
                            pass
                        return JSONResponse(
                            result.model_dump(
                                by_alias=True, mode="json", exclude_none=True
                            )
                        )
                    elif method == "elicitation/create":
                        req = ServerRequest(
                            ElicitRequest(
                                method="elicitation/create",
                                params=ElicitRequestParams(**params),
                            )
                        )
                        result = await latest_session.send_request(  # type: ignore[attr-defined]
                            request=req,
                            result_type=ElicitResult,
                        )
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                            )
                        except Exception:
                            pass
                        return JSONResponse(
                            result.model_dump(
                                by_alias=True, mode="json", exclude_none=True
                            )
                        )
                    elif method == "roots/list":
                        req = ServerRequest(ListRootsRequest(method="roots/list"))
                        result = await latest_session.send_request(  # type: ignore[attr-defined]
                            request=req,
                            result_type=ListRootsResult,
                        )
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                            )
                        except Exception:
                            pass
                        return JSONResponse(
                            result.model_dump(
                                by_alias=True, mode="json", exclude_none=True
                            )
                        )
                    elif method == "ping":
                        req = ServerRequest(PingRequest(method="ping"))
                        result = await latest_session.send_request(  # type: ignore[attr-defined]
                            request=req,
                            result_type=EmptyResult,
                        )
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                            )
                        except Exception:
                            pass
                        return JSONResponse(
                            result.model_dump(
                                by_alias=True, mode="json", exclude_none=True
                            )
                        )
                except Exception as e_latest:
                    logger.warning(
                        f"[request] latest session delivery failed for execution_id={execution_id} method={method}: {e_latest}"
                    )

            # Fallback to mapped session
            session = await _get_session(execution_id)
            if not session:
                logger.warning(
                    f"[request] session_not_available for execution_id={execution_id}"
                )
                return JSONResponse({"error": "session_not_available"}, status_code=503)

            try:
                # Prefer generic request passthrough if available
                rpc = getattr(session, "rpc", None)
                if rpc and hasattr(rpc, "request"):
                    result = await rpc.request(method, params)
                    try:
                        logger.debug(
                            f"[request] forwarded generic request '{method}' to session_id={id(session)}"
                        )
                    except Exception:
                        pass
                    return JSONResponse(result)
                # Fallback: Map a small set of supported server->client requests
                if method == "sampling/createMessage":
                    req = ServerRequest(
                        CreateMessageRequest(
                            method="sampling/createMessage",
                            params=CreateMessageRequestParams(**params),
                        )
                    )
                    result = await session.send_request(  # type: ignore[attr-defined]
                        request=req,
                        result_type=CreateMessageResult,
                    )
                    return JSONResponse(
                        result.model_dump(by_alias=True, mode="json", exclude_none=True)
                    )
                elif method == "elicitation/create":
                    req = ServerRequest(
                        ElicitRequest(
                            method="elicitation/create",
                            params=ElicitRequestParams(**params),
                        )
                    )
                    result = await session.send_request(  # type: ignore[attr-defined]
                        request=req,
                        result_type=ElicitResult,
                    )
                    return JSONResponse(
                        result.model_dump(by_alias=True, mode="json", exclude_none=True)
                    )
                elif method == "roots/list":
                    req = ServerRequest(ListRootsRequest(method="roots/list"))
                    result = await session.send_request(  # type: ignore[attr-defined]
                        request=req,
                        result_type=ListRootsResult,
                    )
                    return JSONResponse(
                        result.model_dump(by_alias=True, mode="json", exclude_none=True)
                    )
                elif method == "ping":
                    req = ServerRequest(PingRequest(method="ping"))
                    result = await session.send_request(  # type: ignore[attr-defined]
                        request=req,
                        result_type=EmptyResult,
                    )
                    return JSONResponse(
                        result.model_dump(by_alias=True, mode="json", exclude_none=True)
                    )
                else:
                    return JSONResponse(
                        {"error": f"unsupported method: {method}"}, status_code=400
                    )
            except Exception as e:
                try:
                    logger.error(
                        f"[request] error forwarding for execution_id={execution_id} method={method}: {e}"
                    )
                except Exception:
                    pass
                return JSONResponse({"error": str(e)}, status_code=500)

        @mcp_server.custom_route(
            "/internal/workflows/log", methods=["POST"], include_in_schema=False
        )
        async def _internal_workflows_log(request: Request):
            body = await request.json()
            execution_id = body.get("execution_id")
            level = str(body.get("level", "info")).lower()
            namespace = body.get("namespace") or "mcp_agent"
            message = body.get("message") or ""
            data = body.get("data") or {}
            try:
                logger.info(
                    f"[log] incoming execution_id={execution_id} level={level} ns={namespace}"
                )
            except Exception:
                pass

            # Optional shared-secret auth
            gw_token = os.environ.get("MCP_GATEWAY_TOKEN")
            if gw_token:
                bearer = request.headers.get("Authorization", "")
                bearer_token = (
                    bearer.split(" ", 1)[1]
                    if bearer.lower().startswith("bearer ")
                    else ""
                )
                header_tok = request.headers.get("X-MCP-Gateway-Token", "")
                if not (
                    secrets.compare_digest(header_tok, gw_token)
                    or secrets.compare_digest(bearer_token, gw_token)
                ):
                    return JSONResponse(
                        {"ok": False, "error": "unauthorized"}, status_code=401
                    )

            # Prefer latest upstream session first
            latest_session = _get_fallback_upstream_session()
            if latest_session is not None:
                try:
                    await latest_session.send_log_message(  # type: ignore[attr-defined]
                        level=level,  # type: ignore[arg-type]
                        data={
                            "message": message,
                            "namespace": namespace,
                            "data": data,
                        },
                        logger=namespace,
                    )
                    logger.debug(
                        f"[log] delivered via latest session_id={id(latest_session)} level={level} ns={namespace}"
                    )
                    try:
                        await _register_session(
                            run_id=execution_id,
                            execution_id=execution_id,
                            session=latest_session,
                        )
                        logger.info(
                            f"[log] rebound mapping to latest session_id={id(latest_session)} for execution_id={execution_id}"
                        )
                    except Exception:
                        pass
                    return JSONResponse({"ok": True})
                except Exception as e_latest:
                    logger.warning(
                        f"[log] latest session delivery failed for execution_id={execution_id}: {e_latest}"
                    )

            # Fallback to mapped session
            session = await _get_session(execution_id)
            if not session:
                logger.warning(
                    f"[log] session_not_available for execution_id={execution_id}"
                )
                return JSONResponse(
                    {"ok": False, "error": "session_not_available"}, status_code=503
                )
            if level not in ("debug", "info", "warning", "error"):
                level = "info"
            try:
                await session.send_log_message(
                    level=level,  # type: ignore[arg-type]
                    data={
                        "message": message,
                        "namespace": namespace,
                        "data": data,
                    },
                    logger=namespace,
                )
                return JSONResponse({"ok": True})
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

        @mcp_server.custom_route(
            "/internal/human/prompts", methods=["POST"], include_in_schema=False
        )
        async def _internal_human_prompts(request: Request):
            body = await request.json()
            execution_id = body.get("execution_id")
            prompt = body.get("prompt") or {}
            metadata = body.get("metadata") or {}
            try:
                logger.info(
                    f"[human] incoming execution_id={execution_id} signal_name={metadata.get('signal_name', 'human_input')}"
                )
            except Exception:
                pass

            # Optional shared-secret auth
            gw_token = os.environ.get("MCP_GATEWAY_TOKEN")
            if gw_token:
                bearer = request.headers.get("Authorization", "")
                bearer_token = (
                    bearer.split(" ", 1)[1]
                    if bearer.lower().startswith("bearer ")
                    else ""
                )
                header_tok = request.headers.get("X-MCP-Gateway-Token", "")
                if not (
                    secrets.compare_digest(header_tok, gw_token)
                    or secrets.compare_digest(bearer_token, gw_token)
                ):
                    return JSONResponse({"error": "unauthorized"}, status_code=401)

            # Prefer latest upstream session first
            latest_session = _get_fallback_upstream_session()
            import uuid

            request_id = str(uuid.uuid4())
            payload = {
                "kind": "human_input_request",
                "request_id": request_id,
                "prompt": prompt if isinstance(prompt, dict) else {"text": str(prompt)},
                "metadata": metadata,
            }
            try:
                # Store pending prompt correlation for submit tool
                async with _PENDING_PROMPTS_LOCK:
                    _PENDING_PROMPTS[request_id] = {
                        "workflow_id": metadata.get("workflow_id"),
                        "execution_id": execution_id,
                        "signal_name": metadata.get("signal_name", "human_input"),
                        "session_id": metadata.get("session_id"),
                    }
                # Try latest first
                if latest_session is not None:
                    try:
                        await latest_session.send_log_message(  # type: ignore[attr-defined]
                            level="info",  # type: ignore[arg-type]
                            data=payload,
                            logger="mcp_agent.human",
                        )
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                            )
                            logger.info(
                                f"[human] rebound mapping to latest session_id={id(latest_session)} for execution_id={execution_id}"
                            )
                        except Exception:
                            pass
                        return JSONResponse({"request_id": request_id})
                    except Exception as e_latest:
                        logger.warning(
                            f"[human] latest session delivery failed for execution_id={execution_id}: {e_latest}"
                        )

                # Fallback to mapped session
                session = await _get_session(execution_id)
                if not session:
                    return JSONResponse(
                        {"error": "session_not_available"}, status_code=503
                    )
                await session.send_log_message(
                    level="info",  # type: ignore[arg-type]
                    data=payload,
                    logger="mcp_agent.human",
                )
                return JSONResponse({"request_id": request_id})
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

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
        # Install internal HTTP routes
        try:
            _install_internal_routes(mcp)
        except Exception:
            pass
    else:
        mcp = FastMCP(
            name=app.name or "mcp_agent_server",
            # TODO: saqadri (MAC) - create a much more detailed description
            # based on all the available agents and workflows,
            # or use the MCPApp's description if available.
            instructions=f"MCP server exposing {app.name} workflows and agents as tools. Description: {app.description}",
            lifespan=app_specific_lifespan,
            **kwargs,
        )
        # Store the server on the app so it's discoverable and can be extended further
        app.mcp = mcp
        setattr(mcp, "_mcp_agent_app", app)
        # Install internal HTTP routes
        try:
            _install_internal_routes(mcp)
        except Exception:
            pass

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
        # Ensure upstream session is set for any logs emitted during this call
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
        result: Dict[str, Dict[str, Any]] = {}
        workflows, _ = _resolve_workflows_and_context(ctx)
        workflows = workflows or {}
        for workflow_name, workflow_cls in workflows.items():
            # Determine parameter schema (strip self / prefer original function)
            run_fn_tool = _build_run_param_tool(workflow_cls)

            # Determine endpoints based on whether this is an auto sync/async tool
            if getattr(workflow_cls, "__mcp_agent_sync_tool__", False):
                endpoints = [
                    f"{workflow_name}",
                ]
            elif getattr(workflow_cls, "__mcp_agent_async_tool__", False):
                endpoints = [
                    f"{workflow_name}",
                ]
            else:
                endpoints = [
                    f"workflows-{workflow_name}-run",
                ]

            result[workflow_name] = {
                "name": workflow_name,
                "description": workflow_cls.__doc__ or run_fn_tool.description,
                "capabilities": ["run"],
                "tool_endpoints": endpoints,
                "run_parameters": run_fn_tool.parameters,
            }

        return result

    @mcp.tool(name="workflows-runs-list")
    async def list_workflow_runs(
        ctx: MCPContext,
        limit: int = 100,
        page_size: int | None = 100,
        next_page_token: str | None = None,
    ) -> List[Dict[str, Any]] | WorkflowRunsPage:
        """
        List all workflow instances (runs) with their detailed status information.

        This returns information about actual workflow instances (runs), not workflow types.
        For each running workflow, returns its ID, name, current state, and available operations.
        This helps in identifying and managing active workflow instances.


        Args:
            limit: Maximum number of runs to return. Default: 100.
            page_size: Page size for paginated backends. Default: 100.
            next_page_token: Optional Base64-encoded token for pagination resume. Only provide if you received a next_page_token from a previous call.

        Returns:
            A list of workflow run status dictionaries with detailed workflow information.
        """
        # Ensure upstream session is set for any logs emitted during this call
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass

        server_context = getattr(
            ctx.request_context, "lifespan_context", None
        ) or _get_attached_server_context(ctx.fastmcp)
        if server_context is None or not hasattr(server_context, "workflow_registry"):
            raise ToolError("Server context not available for MCPApp Server.")

        # Decode next_page_token if provided (base64-encoded string -> bytes)
        token_bytes = None
        if next_page_token:
            try:
                import base64 as _b64

                token_bytes = _b64.b64decode(next_page_token)
            except Exception:
                token_bytes = None

        # Get workflow statuses from the registry with pagination/query hints
        workflow_statuses = (
            await server_context.workflow_registry.list_workflow_statuses(
                query=None,
                limit=limit,
                page_size=page_size,
                next_page_token=token_bytes,
            )
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
        # Ensure upstream session is set before starting the workflow
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
        return await _workflow_run(ctx, workflow_name, run_parameters, **kwargs)

    @mcp.tool(name="workflows-get_status")
    async def get_workflow_status(
        ctx: MCPContext,
        run_id: str | None = None,
        workflow_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Get the status of a running workflow.

        Provides detailed information about a workflow instance including its current state,
        whether it's running or completed, and any results or errors encountered.

        Args:
            run_id: Optional run ID of the workflow to check.
                If omitted, the server will use the latest run for the workflow_id provided.
                Received from workflows/run or workflows/runs/list.
            workflow_id: Optional workflow identifier (usually the tool/workflow name).
                If omitted, the server will infer it from the run metadata when possible.
                Received from workflows/run or workflows/runs/list.

        Returns:
            A dictionary with comprehensive information about the workflow status.
        """
        # Ensure upstream session is available for any status-related logs
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
        # Opportunistically re-bind the upstream session mapping to this request's session
        try:
            sess = getattr(ctx, "session", None)
            if sess and run_id:
                exec_id = _RUN_EXECUTION_ID_REGISTRY.get(run_id, run_id)
                await _register_session(
                    run_id=run_id, execution_id=exec_id, session=sess
                )
        except Exception:
            pass
        return await _workflow_status(ctx, run_id=run_id, workflow_id=workflow_id)

    @mcp.tool(name="workflows-resume")
    async def resume_workflow(
        ctx: MCPContext,
        run_id: str | None = None,
        workflow_id: str | None = None,
        signal_name: str | None = "resume",
        payload: Dict[str, Any] | None = None,
    ) -> bool:
        """
        Resume a paused workflow.

        Args:
            run_id: The ID of the workflow to resume,
                received from workflows/run or workflows/runs/list.
                If not specified, the latest run for the workflow_id will be used.
            workflow_id: The ID of the workflow to resume,
                received from workflows/run or workflows/runs/list.
            signal_name: Optional name of the signal to send to resume the workflow.
                This will default to "resume", but can be a custom signal name
                if the workflow was paused on a specific signal.
            payload: Optional payload to provide the workflow upon resumption.
                For example, if a workflow is waiting for human input,
                this can be the human input.

        Returns:
            True if the workflow was resumed, False otherwise.
        """
        # Ensure upstream session is available for any status-related logs
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
        # Re-bind mapping for this run to ensure worker notifies reach the current client session
        try:
            sess = getattr(ctx, "session", None)
            if sess and run_id:
                exec_id = _RUN_EXECUTION_ID_REGISTRY.get(run_id, run_id)
                await _register_session(
                    run_id=run_id, execution_id=exec_id, session=sess
                )
        except Exception:
            pass

        if run_id is None and workflow_id is None:
            raise ToolError("Either run_id or workflow_id must be provided.")

        workflow_registry: WorkflowRegistry | None = _resolve_workflow_registry(ctx)

        if not workflow_registry:
            raise ToolError("Workflow registry not found for MCPApp Server.")

        logger.info(
            f"Resuming workflow ID {workflow_id or 'unknown'}, run ID {run_id or 'unknown'} with signal '{signal_name}' and payload '{payload}'"
        )

        # Get the workflow instance from the registry
        result = await workflow_registry.resume_workflow(
            run_id=run_id,
            workflow_id=workflow_id,
            signal_name=signal_name,
            payload=payload,
        )

        if result:
            logger.debug(
                f"Signaled workflow ID {workflow_id or 'unknown'}, run ID {run_id or 'unknown'} with signal '{signal_name}' and payload '{payload}'"
            )
        else:
            logger.error(
                f"Failed to signal workflow ID {workflow_id or 'unknown'}, run ID {run_id or 'unknown'} with signal '{signal_name}' and payload '{payload}'"
            )

        return result

    @mcp.tool(name="workflows-cancel")
    async def cancel_workflow(
        ctx: MCPContext, run_id: str | None = None, workflow_id: str | None = None
    ) -> bool:
        """
        Cancel a running workflow.

        Args:
            run_id: The ID of the workflow instance to cancel,
                received from workflows/run or workflows/runs/list.
                If not provided, will attempt to cancel the latest run for the
                provided workflow ID.
            workflow_id: The ID of the workflow to cancel,
                received from workflows/run or workflows/runs/list.

        Returns:
            True if the workflow was cancelled, False otherwise.
        """
        # Ensure upstream session is available for any status-related logs
        try:
            _set_upstream_from_request_ctx_if_available(ctx)
        except Exception:
            pass
        # Re-bind mapping for this run to ensure worker notifies reach the current client session
        try:
            sess = getattr(ctx, "session", None)
            if sess and run_id:
                exec_id = _RUN_EXECUTION_ID_REGISTRY.get(run_id, run_id)
                await _register_session(
                    run_id=run_id, execution_id=exec_id, session=sess
                )
        except Exception:
            pass

        if run_id is None and workflow_id is None:
            raise ToolError("Either run_id or workflow_id must be provided.")

        workflow_registry: WorkflowRegistry | None = _resolve_workflow_registry(ctx)

        if not workflow_registry:
            raise ToolError("Workflow registry not found for MCPApp Server.")

        logger.info(
            f"Cancelling workflow ID {workflow_id or 'unknown'}, run ID {run_id or 'unknown'}"
        )

        # Get the workflow instance from the registry
        result = await workflow_registry.cancel_workflow(
            run_id=run_id, workflow_id=workflow_id
        )

        if result:
            logger.debug(
                f"Cancelled workflow ID {workflow_id or 'unknown'}, run ID {run_id or 'unknown'}"
            )
        else:
            logger.error(
                f"Failed to cancel workflow {workflow_id or 'unknown'} with ID {run_id or 'unknown'}"
            )

        return result

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
    import time

    async def _wait_for_completion(
        ctx: MCPContext,
        run_id: str,
        *,
        workflow_id: str | None = None,
        timeout: float | None = None,
        registration_grace: float = 1.0,
        poll_initial: float = 0.05,
        poll_max: float = 1.0,
    ):
        registry = _resolve_workflow_registry(ctx)
        if not registry:
            raise ToolError("Workflow registry not found for MCPApp Server.")

        DEFAULT_SYNC_TOOL_TIMEOUT = 120.0
        overall_timeout = timeout or DEFAULT_SYNC_TOOL_TIMEOUT
        deadline = time.monotonic() + overall_timeout

        def remaining() -> float:
            return max(0.0, deadline - time.monotonic())

        async def _await_task(task: asyncio.Task):
            return await asyncio.wait_for(task, timeout=remaining())

        # Fast path: immediate local task
        try:
            wf = await registry.get_workflow(run_id, workflow_id)
            if wf is not None:
                task = getattr(wf, "_run_task", None)
                if isinstance(task, asyncio.Task):
                    return await _await_task(task)
        except Exception:
            pass

        # Short grace window for registration
        sleep = poll_initial
        grace_deadline = time.monotonic() + registration_grace
        while time.monotonic() < grace_deadline and remaining() > 0:
            try:
                wf = await registry.get_workflow(run_id)
                if wf is not None:
                    task = getattr(wf, "_run_task", None)
                    if isinstance(task, asyncio.Task):
                        return await _await_task(task)
            except Exception:
                pass
            await asyncio.sleep(sleep)
            sleep = min(poll_max, sleep * 1.5)

        # Fallback: status polling (works for external/temporal engines)
        sleep = poll_initial
        while True:
            if remaining() <= 0:
                raise ToolError("Timed out waiting for workflow completion")

            status = await _workflow_status(ctx, run_id, workflow_id)
            s = str(
                status.get("status") or (status.get("state") or {}).get("status") or ""
            ).lower()

            if s in {"completed", "error", "cancelled"}:
                if s == "completed":
                    return status.get("result")
                err = status.get("error") or status
                raise ToolError(f"Workflow ended with status={s}: {err}")

            await asyncio.sleep(sleep)
            sleep = min(poll_max, sleep * 2.0)

    for decl in declared:
        name = decl["name"]
        if name in registered:
            continue
        mode = decl["mode"]
        workflow_name = decl["workflow_name"]
        fn = decl.get("source_fn")
        description = decl.get("description")
        structured_output = decl.get("structured_output")

        # Bind per-iteration values to avoid late-binding closure bugs
        name_local = name
        wname_local = workflow_name

        if mode == "sync" and fn is not None:
            sig = inspect.signature(fn)
            return_ann = sig.return_annotation

            def _make_wrapper(bound_wname: str):
                async def _wrapper(**kwargs):
                    ctx: MCPContext = kwargs.pop("__context__")
                    result_ids = await _workflow_run(ctx, bound_wname, kwargs)
                    run_id = result_ids["run_id"]
                    result = await _wait_for_completion(ctx, run_id)
                    try:
                        from mcp_agent.executor.workflow import WorkflowResult as _WFRes
                    except Exception:
                        _WFRes = None  # type: ignore
                    if _WFRes is not None and isinstance(result, _WFRes):
                        return getattr(result, "value", None)
                    # If status payload returned a dict that looks like WorkflowResult, unwrap safely via 'kind'
                    if (
                        isinstance(result, dict)
                        and result.get("kind") == "workflow_result"
                    ):
                        return result.get("value")
                    return result

                return _wrapper

            _wrapper = _make_wrapper(wname_local)

            ann = dict(getattr(fn, "__annotations__", {}))
            ann.pop("app_ctx", None)

            ctx_param_name = "ctx"
            from mcp.server.fastmcp import Context as _Ctx

            ann[ctx_param_name] = _Ctx
            ann["return"] = getattr(fn, "__annotations__", {}).get("return", return_ann)
            _wrapper.__annotations__ = ann
            _wrapper.__name__ = name_local
            _wrapper.__doc__ = description or (fn.__doc__ or "")

            params = [p for p in sig.parameters.values() if p.name != "app_ctx"]
            ctx_param = inspect.Parameter(
                ctx_param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=_Ctx,
            )
            _wrapper.__signature__ = inspect.Signature(
                parameters=params + [ctx_param], return_annotation=return_ann
            )

            def _make_adapter(context_param_name: str, inner_wrapper):
                async def _adapter(**kw):
                    if context_param_name not in kw:
                        raise ToolError("Context not provided")
                    kw["__context__"] = kw.pop(context_param_name)
                    return await inner_wrapper(**kw)

                _adapter.__annotations__ = _wrapper.__annotations__
                _adapter.__name__ = _wrapper.__name__
                _adapter.__doc__ = _wrapper.__doc__
                _adapter.__signature__ = _wrapper.__signature__
                return _adapter

            _adapter = _make_adapter(ctx_param_name, _wrapper)

            mcp.add_tool(
                _adapter,
                name=name_local,
                description=description or (fn.__doc__ or ""),
                structured_output=structured_output,
            )
            registered.add(name_local)

        elif mode == "async":
            # Use the declared name as the async run endpoint
            run_tool_name = f"{name_local}"

            if run_tool_name not in registered:
                # Build a wrapper mirroring original function params (excluding app_ctx/ctx)
                async def _async_wrapper(**kwargs):
                    ctx: MCPContext = kwargs.pop("__context__")
                    # Start workflow and return workflow_id/run_id (do not wait)
                    return await _workflow_run(ctx, wname_local, kwargs)

                # Mirror original signature and annotations similar to sync path
                ann = dict(getattr(fn, "__annotations__", {}))
                ann.pop("app_ctx", None)
                try:
                    from mcp.server.fastmcp import Context as _Ctx
                except Exception:
                    _Ctx = None  # type: ignore

                # Choose context kw-only parameter
                ctx_param_name = "ctx"
                if _Ctx is not None:
                    ann[ctx_param_name] = _Ctx

                # Async run returns workflow_id/run_id
                from typing import Dict as _Dict  # type: ignore

                ann["return"] = _Dict[str, str]
                _async_wrapper.__annotations__ = ann
                _async_wrapper.__name__ = run_tool_name

                # Description: original docstring + async note
                base_desc = description or (fn.__doc__ or "")
                async_note = (
                    f"\n\nThis tool starts the '{wname_local}' workflow asynchronously and returns "
                    "'workflow_id' and 'run_id'. Use the 'workflows-get_status' tool "
                    "with the returned 'workflow_id' and the returned "
                    "'run_id' to retrieve status/results."
                )
                full_desc = (base_desc or "").strip() + async_note
                _async_wrapper.__doc__ = full_desc

                # Build mirrored signature: drop app_ctx and any FastMCP Context params
                params = []
                try:
                    sig_async = inspect.signature(fn)
                    for p in sig_async.parameters.values():
                        if p.name == "app_ctx":
                            continue
                        if p.name in ("ctx", "context"):
                            continue
                        if (
                            _Ctx is not None
                            and p.annotation is not inspect._empty
                            and p.annotation is _Ctx
                        ):
                            continue
                        params.append(p)
                except Exception:
                    params = []

                # Append kw-only context param
                if _Ctx is not None:
                    ctx_param = inspect.Parameter(
                        ctx_param_name,
                        kind=inspect.Parameter.KEYWORD_ONLY,
                        annotation=_Ctx,
                    )
                else:
                    ctx_param = inspect.Parameter(
                        ctx_param_name,
                        kind=inspect.Parameter.KEYWORD_ONLY,
                    )

                _async_wrapper.__signature__ = inspect.Signature(
                    parameters=params + [ctx_param], return_annotation=ann.get("return")
                )

                # Adapter to map injected FastMCP context kwarg without additional propagation
                def _make_async_adapter(context_param_name: str, inner_wrapper):
                    async def _adapter(**kw):
                        if context_param_name not in kw:
                            raise ToolError("Context not provided")
                        kw["__context__"] = kw.pop(context_param_name)
                        return await inner_wrapper(**kw)

                    _adapter.__annotations__ = _async_wrapper.__annotations__
                    _adapter.__name__ = _async_wrapper.__name__
                    _adapter.__doc__ = _async_wrapper.__doc__
                    _adapter.__signature__ = _async_wrapper.__signature__
                    return _adapter

                _async_adapter = _make_async_adapter(ctx_param_name, _async_wrapper)

                # Register the async run tool
                mcp.add_tool(
                    _async_adapter,
                    name=run_tool_name,
                    description=full_desc,
                    structured_output=False,
                )
                registered.add(run_tool_name)

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

        Returns:
            A dict with workflow_id and run_id for the started workflow run, can be passed to
            workflows/get_status, workflows/resume, and workflows/cancel.
        """,
    )
    async def run(
        ctx: MCPContext,
        run_parameters: Dict[str, Any] | None = None,
    ) -> Dict[str, str]:
        _set_upstream_from_request_ctx_if_available(ctx)
        return await _workflow_run(ctx, workflow_name, run_parameters)


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
    # Use Temporal run_id as the routing key for gateway callbacks.
    # We don't have it until after the workflow is started; we'll register mapping post-start.

    # Resolve workflows and app context irrespective of startup mode
    # This now returns a context with upstream_session already set
    workflows_dict, app_context = _resolve_workflows_and_context(ctx)
    if not workflows_dict or not app_context:
        raise ToolError("Server context not available for MCPApp Server.")

    if workflow_name not in workflows_dict:
        raise ToolError(f"Workflow '{workflow_name}' not found.")

    # Get the workflow class
    workflow_cls = workflows_dict[workflow_name]

    # Bind the app-level logger (cached) to this per-request context so logs
    # emitted from AutoWorkflow path forward upstream even outside request_ctx.
    try:
        app = _get_attached_app(ctx.fastmcp)
        if app is not None and getattr(app, "name", None):
            from mcp_agent.logging.logger import get_logger as _get_logger

            _get_logger(f"mcp_agent.{app.name}", context=app_context)
    except Exception:
        pass

    # Create and initialize the workflow instance using the factory method
    try:
        # Create workflow instance with context that has upstream_session
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

        # Build memo for Temporal runs if gateway info is available
        workflow_memo = None
        try:
            # Prefer explicit kwargs, else infer from request context/headers
            gateway_url = kwargs.get("gateway_url")
            gateway_token = kwargs.get("gateway_token")
            if gateway_token is None:
                if app and app.config and app.config.temporal:
                    gateway_token = app.config.temporal.api_key

            req = getattr(ctx.request_context, "request", None)
            if req is not None:
                h = req.headers
                # Highest precedence: caller-provided full base URL
                header_url = h.get("X-MCP-Gateway-URL") or h.get("X-Forwarded-Url")
                if gateway_url is None and header_url:
                    gateway_url = header_url

                # Token may be provided by the gateway/proxy
                if gateway_token is None:
                    gateway_token = h.get("X-MCP-Gateway-Token")
                if gateway_token is None:
                    # Support Authorization: Bearer <token>
                    auth = h.get("Authorization")
                    if auth and auth.lower().startswith("bearer "):
                        gateway_token = auth.split(" ", 1)[1]

                # Prefer explicit reconstruction from X-Forwarded-* if present
                if gateway_url is None and (h.get("X-Forwarded-Host") or h.get("Host")):
                    proto = h.get("X-Forwarded-Proto") or "http"
                    host = h.get("X-Forwarded-Host") or h.get("Host")
                    prefix = h.get("X-Forwarded-Prefix") or ""
                    if prefix and not prefix.startswith("/"):
                        prefix = "/" + prefix
                    if host:
                        gateway_url = f"{proto}://{host}{prefix}"

                # Fallback to request's base_url which already includes scheme/host and any mount prefix
                if gateway_url is None:
                    try:
                        if getattr(req, "base_url", None):
                            base_url = str(req.base_url).rstrip("/")
                            if base_url and base_url.lower() != "none":
                                gateway_url = base_url
                    except Exception:
                        gateway_url = None

            # Normalize gateway URL if it points to a non-routable bind address
            def _normalize_gateway_url(url: str | None) -> str | None:
                if not url:
                    return url
                try:
                    from urllib.parse import urlparse, urlunparse

                    parsed = urlparse(url)
                    host = parsed.hostname or ""
                    # Replace wildcard binds with a loopback address that's actually connectable
                    if host in ("0.0.0.0", "::", "[::]"):
                        new_host = "127.0.0.1" if host == "0.0.0.0" else "localhost"
                        netloc = parsed.netloc.replace(host, new_host)
                        parsed = parsed._replace(netloc=netloc)
                        return urlunparse(parsed)
                except Exception:
                    pass
                return url

            gateway_url = _normalize_gateway_url(gateway_url)

            # Final fallback: environment variables (useful if proxies don't set headers)
            try:
                import os as _os

                if gateway_url is None:
                    env_url = _os.environ.get("MCP_GATEWAY_URL")
                    if env_url:
                        gateway_url = env_url
                if gateway_token is None:
                    env_tok = _os.environ.get("MCP_GATEWAY_TOKEN")
                    if env_tok:
                        gateway_token = env_tok
            except Exception:
                pass

            if gateway_url or gateway_token:
                workflow_memo = {
                    "gateway_url": gateway_url,
                    "gateway_token": gateway_token,
                }
        except Exception:
            workflow_memo = None

        # Run the workflow asynchronously and get its ID
        execution = await workflow.run_async(
            __mcp_agent_workflow_memo=workflow_memo,
            **run_parameters,
        )

        execution_id = execution.run_id
        logger.info(
            f"Workflow {workflow_name} started execution {execution_id} for workflow ID {execution.workflow_id}, "
            f"run ID {execution.run_id}. Parameters: {run_parameters}"
        )

        # Register upstream session for this run so external workers can proxy logs/prompts
        try:
            await _register_session(
                run_id=execution.run_id,
                execution_id=execution_id,
                session=getattr(ctx, "session", None),
            )
        except Exception:
            pass

        return {
            "workflow_id": execution.workflow_id,
            "run_id": execution.run_id,
            "execution_id": execution_id,
        }

    except Exception as e:
        logger.error(f"Error creating workflow {workflow_name}: {str(e)}")
        raise ToolError(f"Error creating workflow {workflow_name}: {str(e)}") from e


async def _workflow_status(
    ctx: MCPContext, run_id: str | None = None, workflow_id: str | None = None
) -> Dict[str, Any]:
    # Ensure upstream session so status-related logs are forwarded
    try:
        _set_upstream_from_request_ctx_if_available(ctx)
    except Exception:
        pass

    if not (run_id or workflow_id):
        raise ValueError("Either run_id or workflow_id must be provided.")

    workflow_registry: WorkflowRegistry | None = _resolve_workflow_registry(ctx)

    if not workflow_registry:
        raise ToolError("Workflow registry not found for MCPApp Server.")

    if not workflow_id:
        workflow = await workflow_registry.get_workflow(
            run_id=run_id, workflow_id=workflow_id
        )
        if workflow:
            workflow_id = workflow.id or workflow.name

    status = await workflow_registry.get_workflow_status(
        run_id=run_id, workflow_id=workflow_id
    )

    # Cleanup run registry on terminal states
    try:
        state = str(status.get("status", "")).lower()
        if state in ("completed", "error", "cancelled"):
            try:
                await _unregister_session(run_id)
            except Exception:
                pass
    except Exception:
        pass

    return status


# endregion
