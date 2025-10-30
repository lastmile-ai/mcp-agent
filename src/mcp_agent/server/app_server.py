"""
MCPAgentServer - Exposes MCPApp as MCP server, and
mcp-agent workflows and agents as MCP tools.
"""

from __future__ import annotations

import json
import time
import httpx
import os
import secrets
import asyncio

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set, Tuple, Type
from pydantic import BaseModel, Field
from contextvars import ContextVar, Token
from urllib.parse import parse_qs, urlparse
from json import JSONDecodeError

from mcp.server.fastmcp import Context as MCPContext, FastMCP
from mcp.server.fastmcp.server import AuthSettings
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools import Tool as FastTool

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp_agent.app import MCPApp, phetch
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
from mcp_agent.core.context import Context
from mcp_agent.core.request_context import (
    get_current_request_context,
    reset_current_request_context,
    set_current_request_context,
)
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.oauth.identity import (
    OAuthUserIdentity,
    DEFAULT_PRECONFIGURED_IDENTITY,
    session_identity as _session_identity_from_value,
)
from mcp_agent.oauth.callbacks import callback_registry
from mcp_agent.server.token_verifier import MCPAgentTokenVerifier
from mcp_agent.oauth.errors import (
    AuthorizationDeclined,
    CallbackTimeoutError,
    OAuthFlowError,
)
from mcp_agent.oauth.records import TokenRecord

logger = get_logger(__name__)
# Simple in-memory registry mapping workflow execution_id -> upstream session handle.
# Allows external workers (e.g., Temporal) to relay logs/prompts through MCPApp.
_RUN_SESSION_REGISTRY: Dict[str, Any] = {}
_RUN_EXECUTION_ID_REGISTRY: Dict[str, str] = {}
_RUN_IDENTITY_REGISTRY: Dict[str, OAuthUserIdentity] = {}
_RUN_LOGGING_SESSION: Dict[str, str] = {}
_RUN_CONTEXT_REGISTRY: Dict[str, Context] = {}
_RUN_SESSION_LOCK = asyncio.Lock()
_PENDING_PROMPTS: Dict[str, Dict[str, Any]] = {}
_PENDING_PROMPTS_LOCK = asyncio.Lock()
_IDEMPOTENCY_KEYS_SEEN: Dict[str, Set[str]] = {}
_IDEMPOTENCY_KEYS_LOCK = asyncio.Lock()

_CURRENT_IDENTITY: ContextVar[OAuthUserIdentity | None] = ContextVar(
    "mcp_current_identity", default=None
)


def _clear_cached_session_refs(target: Any, session: Any | None) -> None:
    if target is None or session is None:
        return
    try:
        if getattr(target, "_last_known_upstream_session", None) is session:
            setattr(target, "_last_known_upstream_session", None)
    except Exception:
        pass


async def _register_session(
    run_id: str,
    execution_id: str,
    session: Any,
    identity: OAuthUserIdentity | None = None,
    context: "Context" | None = None,
    session_id: str | None = None,
) -> None:
    async with _RUN_SESSION_LOCK:
        _RUN_SESSION_REGISTRY[execution_id] = session
        _RUN_EXECUTION_ID_REGISTRY[run_id] = execution_id
        if identity is not None:
            _RUN_IDENTITY_REGISTRY[execution_id] = identity
        if context is not None:
            _RUN_CONTEXT_REGISTRY[execution_id] = context
        resolved_session_id = (
            session_id
            or getattr(context, "request_session_id", None)
            or getattr(identity, "subject", None)
        )
        if resolved_session_id:
            _RUN_LOGGING_SESSION[execution_id] = resolved_session_id
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
            session = _RUN_SESSION_REGISTRY.pop(execution_id, None)
            _RUN_IDENTITY_REGISTRY.pop(execution_id, None)
            context_ref = _RUN_CONTEXT_REGISTRY.pop(execution_id, None)
            _RUN_LOGGING_SESSION.pop(execution_id, None)
            if context_ref is not None:
                app_ref = getattr(context_ref, "app", None)
                _clear_cached_session_refs(context_ref, session)
                if app_ref is not None:
                    _clear_cached_session_refs(app_ref, session)
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


def _get_identity_for_execution(execution_id: str) -> OAuthUserIdentity | None:
    return _RUN_IDENTITY_REGISTRY.get(execution_id)


def _get_context_for_execution(execution_id: str) -> "Context" | None:
    return _RUN_CONTEXT_REGISTRY.get(execution_id)


def _set_current_identity(identity: OAuthUserIdentity | None) -> None:
    _CURRENT_IDENTITY.set(identity)


def get_current_identity() -> OAuthUserIdentity | None:
    return _CURRENT_IDENTITY.get()


def _resolve_identity_for_request(
    ctx: MCPContext | None = None,
    app_context: "Context" | None = None,
    execution_id: str | None = None,
) -> OAuthUserIdentity:
    identity = _CURRENT_IDENTITY.get()
    if identity is None and execution_id:
        identity = _get_identity_for_execution(execution_id)
    request_session_id: str | None = None
    if ctx is not None:
        request_session_id = _extract_session_id_from_context(ctx)
    if app_context is None and ctx is not None:
        app = _get_attached_app(ctx.fastmcp)
        if app is not None and getattr(app, "context", None) is not None:
            app_context = app.context
    if identity is None and request_session_id:
        resolved = get_identity_for_session(request_session_id, app_context)
        if resolved:
            logger.debug(
                "Resolved identity from session registry",
                data={
                    "session_id": request_session_id,
                    "identity": resolved.cache_key,
                },
            )
            identity = resolved
    if identity is None and app_context is not None:
        session_id = getattr(app_context, "session_id", None)
        if session_id and session_id != request_session_id:
            identity = get_identity_for_session(session_id, app_context)
    if identity is None:
        identity = DEFAULT_PRECONFIGURED_IDENTITY
    return identity


def get_identity_for_session(
    session_id: str | None, app_context: "Context" | None = None
) -> OAuthUserIdentity | None:
    """Lookup the cached identity for a given MCP session."""
    if not session_id:
        return None
    if app_context is not None:
        try:
            identity = app_context.identity_registry.get(session_id)
            if identity is not None:
                return identity
        except Exception:
            pass
    else:
        logger.debug(
            "No app context provided when resolving session identity",
            data={"session_id": session_id},
        )
    return _session_identity_from_value(session_id)


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


def _enter_request_context(
    ctx: MCPContext | None,
) -> Tuple[Optional["Context"], Token | None]:
    """Prepare and bind a per-request context, returning it alongside the contextvar token."""
    if ctx is None:
        return None, None

    try:
        session = ctx.session
    except (AttributeError, ValueError):
        session = None

    session_id = _extract_session_id_from_context(ctx)
    identity: OAuthUserIdentity | None = None
    try:
        auth_user = auth_context_var.get()
    except LookupError:
        auth_user = None

    if isinstance(auth_user, AuthenticatedUser):
        access_token = getattr(auth_user, "access_token", None)
        if access_token is not None:
            try:
                from mcp_agent.oauth.access_token import MCPAccessToken

                if isinstance(access_token, MCPAccessToken):
                    identity = OAuthUserIdentity.from_access_token(access_token)
                else:
                    token_dict = getattr(access_token, "model_dump", None)
                    if callable(token_dict):
                        maybe_token = MCPAccessToken.model_validate(token_dict())
                        if maybe_token is not None:
                            identity = OAuthUserIdentity.from_access_token(maybe_token)
            except Exception:
                identity = None

    base_context: Context | None = None
    lifespan_ctx = getattr(ctx.request_context, "lifespan_context", None)
    if (
        lifespan_ctx is not None
        and hasattr(lifespan_ctx, "context")
        and getattr(lifespan_ctx, "context", None) is not None
    ):
        base_context = lifespan_ctx.context

    if base_context is None:
        app: MCPApp | None = _get_attached_app(ctx.fastmcp)
        if app is not None and getattr(app, "context", None) is not None:
            base_context = app.context

    if identity is None and session_id:
        identity = _session_identity_from_value(session_id)

    if identity is None:
        identity = DEFAULT_PRECONFIGURED_IDENTITY

    bound_context: Context | None = None
    token: Token | None = None

    if base_context is not None:
        previous_session = None
        try:
            previous_session = getattr(base_context, "upstream_session", None)
        except Exception:
            previous_session = None
        bound_context = base_context.bind_request(
            getattr(ctx, "request_context", None),
            getattr(ctx, "fastmcp", None),
        )
        if session is not None:
            bound_context.upstream_session = session
        try:
            setattr(bound_context, "_scoped_upstream_session", session)
        except Exception:
            pass
        try:
            setattr(bound_context, "_previous_upstream_session", previous_session)
        except Exception:
            pass
        bound_context.request_session_id = session_id
        bound_context.request_identity = identity
        token = set_current_request_context(bound_context)
        try:
            setattr(bound_context, "_base_context_ref", base_context)
        except Exception:
            pass
        if session is not None:
            try:
                setattr(base_context, "_last_known_upstream_session", session)
            except Exception:
                pass
            app_ref = getattr(base_context, "app", None)
            if app_ref is not None:
                try:
                    setattr(app_ref, "_last_known_upstream_session", session)
                except Exception:
                    pass
        if session_id and identity is not None:
            try:
                base_context.identity_registry[session_id] = identity
                logger.debug(
                    "Registered identity for session",
                    data={"session_id": session_id, "identity": identity.cache_key},
                )
            except Exception:
                pass
    else:
        token = None

    _set_current_identity(identity)
    return bound_context, token


def _exit_request_context(
    bound_context: Optional["Context"], token: Token | None = None
) -> None:
    reset_current_request_context(token)
    try:
        _set_current_identity(None)
    except Exception:
        pass

    if not isinstance(bound_context, Context):
        return

    base_context = getattr(bound_context, "_base_context_ref", None) or getattr(
        bound_context, "_parent_context", None
    )
    session = getattr(bound_context, "_scoped_upstream_session", None)
    targets: list[Any] = []
    app_ref = None
    if base_context is not None:
        targets.append(base_context)
        app_ref = getattr(base_context, "app", None)
        if app_ref is not None:
            targets.append(app_ref)

    for target in targets:
        _clear_cached_session_refs(target, session)

    if base_context is not None and session is not None:
        previous_session = getattr(bound_context, "_previous_upstream_session", None)
        try:
            if getattr(base_context, "upstream_session", None) is session:
                base_context.upstream_session = previous_session
        except Exception:
            pass
        if app_ref is not None:
            try:
                if getattr(app_ref, "upstream_session", None) is session:
                    app_ref.upstream_session = previous_session
            except Exception:
                pass

    for attr in (
        "_base_context_ref",
        "_scoped_upstream_session",
        "_previous_upstream_session",
    ):
        try:
            delattr(bound_context, attr)
        except Exception:
            pass


def _resolve_workflows_and_context(
    ctx: MCPContext,
    bound_context: Optional["Context"] = None,
) -> Tuple[Dict[str, Type["Workflow"]] | None, Optional["Context"]]:
    """Resolve the workflows mapping and underlying app context regardless of startup mode.

    Tries lifespan ServerContext first (including compatible mocks), then attached app.
    """
    lifespan_ctx = getattr(ctx.request_context, "lifespan_context", None)
    if (
        lifespan_ctx is not None
        and hasattr(lifespan_ctx, "workflows")
        and hasattr(lifespan_ctx, "context")
    ):
        workflows = lifespan_ctx.workflows
        context = bound_context or getattr(lifespan_ctx, "context", None)
        return workflows, context

    app: MCPApp | None = _get_attached_app(ctx.fastmcp)

    if app is not None:
        return app.workflows, bound_context or app.context

    return None, bound_context


def _resolve_workflows_and_context_safe(
    ctx: MCPContext, bound_context: Optional["Context"] = None
) -> Tuple[Dict[str, Type["Workflow"]] | None, Optional["Context"]]:
    resolver = _resolve_workflows_and_context
    try:
        return resolver(ctx, bound_context)
    except TypeError:
        # Backwards compatibility with mocks/tests that expect the older signature.
        return resolver(ctx)  # type: ignore[misc]


def _extract_session_id_from_context(ctx: MCPContext) -> str | None:
    """Attempt to extract the caller's MCP session identifier from the request context."""
    # Request-level meta (top-level)
    try:
        meta = getattr(ctx.request_context, "meta", None)
        if meta is not None:
            extra = getattr(meta, "model_extra", {}) or {}
            session_id = (
                getattr(meta, "sessionId", None)
                or getattr(meta, "session_id", None)
                or extra.get("sessionId")
                or extra.get("session_id")
            )
            if session_id:
                return str(session_id)
    except Exception:
        pass

    # Parameters meta within the request payload
    try:
        req = getattr(ctx.request_context, "request", None)
        if req is not None:
            root = getattr(req, "root", None)
            params = getattr(root, "params", None)
            meta = getattr(params, "meta", None)
            if meta is not None:
                extra = getattr(meta, "model_extra", {}) or {}
                session_id = (
                    getattr(meta, "sessionId", None)
                    or getattr(meta, "session_id", None)
                    or extra.get("sessionId")
                    or extra.get("session_id")
                )
                if session_id:
                    return str(session_id)

            query_params = getattr(req, "query_params", None)
            if query_params is not None:
                if "session_id" in query_params:
                    return query_params.get("session_id")
    except Exception:
        pass

    return None


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

    auth_settings_config = None
    try:
        if app.context and app.context.config:
            auth_settings_config = app.context.config.authorization
    except Exception:
        auth_settings_config = None

    effective_auth_settings: AuthSettings | None = None
    token_verifier: MCPAgentTokenVerifier | None = None
    owns_token_verifier = False
    if auth_settings_config and auth_settings_config.enabled:
        try:
            effective_auth_settings = AuthSettings(
                issuer_url=auth_settings_config.issuer_url,  # type: ignore[arg-type]
                resource_server_url=auth_settings_config.resource_server_url,  # type: ignore[arg-type]
                service_documentation_url=auth_settings_config.service_documentation_url,  # type: ignore[arg-type]
                required_scopes=auth_settings_config.required_scopes or None,
            )
            token_verifier = MCPAgentTokenVerifier(auth_settings_config)
        except Exception as exc:
            logger.error(
                "Failed to configure authorization server integration",
                exc_info=True,
                data={"error": str(exc)},
            )
            effective_auth_settings = None
            token_verifier = None

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
            if owns_token_verifier and token_verifier is not None:
                try:
                    await token_verifier.aclose()
                except Exception:
                    pass

    # Helper: install internal HTTP routes (not MCP tools)
    def _install_internal_routes(mcp_server: FastMCP) -> None:
        def _get_fallback_upstream_session() -> Any | None:
            """Best-effort fallback to the most recent upstream session captured on the app context.

            This helps when a workflow run's mapping has not been refreshed after a client reconnect.
            """
            active_ctx = None
            try:
                active_ctx = get_current_request_context()
            except Exception:
                active_ctx = None
            if active_ctx is not None:
                try:
                    upstream = getattr(active_ctx, "upstream_session", None)
                    if upstream is not None:
                        return upstream
                except Exception:
                    pass

            try:
                app_obj: MCPApp | None = _get_attached_app(mcp_server)
            except Exception:
                app_obj = None

            if not app_obj:
                return None

            for candidate in (
                getattr(app_obj, "_last_known_upstream_session", None),
                getattr(app_obj, "_upstream_session", None),
            ):
                if candidate is not None:
                    return candidate

            base_ctx = getattr(app_obj, "context", None)
            if base_ctx is None:
                return None

            for candidate in (
                getattr(base_ctx, "_last_known_upstream_session", None),
                getattr(base_ctx, "_upstream_session", None),
            ):
                if candidate is not None:
                    return candidate

            return None

        @mcp_server.custom_route(
            "/internal/oauth/callback/{flow_id}",
            methods=["GET", "POST"],
            include_in_schema=False,
        )
        async def _oauth_callback(request: Request):
            flow_id = request.path_params.get("flow_id")
            if not flow_id:
                return JSONResponse({"error": "missing_flow_id"}, status_code=400)

            payload: Dict[str, Any] = {}
            try:
                payload.update({k: v for k, v in request.query_params.multi_items()})
            except Exception:
                payload.update(dict(request.query_params))

            if request.method.upper() == "POST":
                content_type = request.headers.get("content-type", "")
                try:
                    if "application/json" in content_type:
                        body_data = await request.json()
                    else:
                        form = await request.form()
                        body_data = {k: v for k, v in form.multi_items()}
                except Exception:
                    body_data = {}
                payload.update(body_data)

            delivered = await callback_registry.deliver(flow_id, payload)
            if not delivered:
                return JSONResponse({"error": "unknown_flow"}, status_code=404)

            html = """<!DOCTYPE html><html><body><h3>Authorization complete.</h3><p>You may close this window and return to MCP Agent.</p></body></html>"""
            return HTMLResponse(html)

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
            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )

            # Check authentication
            auth_error = _check_gateway_auth(request)
            if auth_error:
                return auth_error

            # Optional idempotency handling
            idempotency_key = params.get("idempotency_key")
            if idempotency_key:
                async with _IDEMPOTENCY_KEYS_LOCK:
                    seen = _IDEMPOTENCY_KEYS_SEEN.setdefault(execution_id or "", set())
                    if idempotency_key in seen:
                        return JSONResponse({"ok": True, "idempotent": True})
                    seen.add(idempotency_key)

            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )

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
                        identity = _get_identity_for_execution(execution_id)
                        existing_context = _get_context_for_execution(execution_id)
                        await _register_session(
                            run_id=execution_id,
                            execution_id=execution_id,
                            session=latest_session,
                            identity=identity,
                            context=existing_context,
                            session_id=getattr(
                                existing_context, "request_session_id", None
                            ),
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
            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )
            if not mapped_session:
                logger.warning(
                    f"[notify] session_not_available for execution_id={execution_id} (tried_latest={tried_latest})"
                )
                return JSONResponse(
                    {"ok": False, "error": "session_not_available"}, status_code=503
                )

            ctx_token: Token | None = None
            if mapped_context is not None:
                ctx_token = set_current_request_context(mapped_context)

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
            finally:
                reset_current_request_context(ctx_token)

        # Helper function for shared authentication
        def _check_gateway_auth(request: Request) -> JSONResponse | None:
            """
            Check optional shared-secret authentication for internal endpoints.
            Returns JSONResponse with error if auth fails, None if auth passes.
            """
            gw_token = os.environ.get("MCP_GATEWAY_TOKEN")
            if not gw_token:
                return None  # No auth required if no token is set

            bearer = request.headers.get("Authorization", "")
            bearer_token = (
                bearer.split(" ", 1)[1] if bearer.lower().startswith("bearer ") else ""
            )
            header_tok = request.headers.get("X-MCP-Gateway-Token", "")

            if not (
                secrets.compare_digest(header_tok, gw_token)
                or secrets.compare_digest(bearer_token, gw_token)
            ):
                return JSONResponse(
                    {"ok": False, "error": "unauthorized"}, status_code=401
                )

            return None  # Auth passed

        # Helper functions for request handling
        async def _handle_request_via_rpc(
            session,
            method: str,
            params: dict,
            execution_id: str,
            log_prefix: str = "request",
        ):
            """Handle request via generic RPC if available."""
            rpc = getattr(session, "rpc", None)
            if rpc and hasattr(rpc, "request"):
                result = await rpc.request(method, params)
                logger.debug(
                    f"[{log_prefix}] delivered via session_id={id(session)} (generic '{method}')"
                )
                return result
            return None

        async def _handle_specific_request(
            session: Any,
            method: str,
            params: dict,
            identity: OAuthUserIdentity,
            context: "Context",
            log_prefix: str = "request",
        ):
            """Handle specific request types with structured request/response."""
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

            if method == "sampling/createMessage":
                req = ServerRequest(
                    CreateMessageRequest(
                        method="sampling/createMessage",
                        params=CreateMessageRequestParams(**params),
                    )
                )
                callback_data = await session.send_request(
                    request=req, result_type=CreateMessageResult
                )  # type: ignore[attr-defined]
                return callback_data.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            elif method == "elicitation/create":
                req = ServerRequest(
                    ElicitRequest(
                        method="elicitation/create",
                        params=ElicitRequestParams(**params),
                    )
                )
                callback_data = await session.send_request(
                    request=req, result_type=ElicitResult
                )  # type: ignore[attr-defined]
                return callback_data.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            elif method == "roots/list":
                req = ServerRequest(ListRootsRequest(method="roots/list"))
                callback_data = await session.send_request(
                    request=req, result_type=ListRootsResult
                )  # type: ignore[attr-defined]
                return callback_data.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            elif method == "ping":
                req = ServerRequest(PingRequest(method="ping"))
                callback_data = await session.send_request(
                    request=req, result_type=EmptyResult
                )  # type: ignore[attr-defined]
                return callback_data.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            elif method == "auth/request":
                # TODO: special handling of auth request, should be replaced by future URL elicitation

                # first check to see if the token is in the cache already
                server_name = params["server_name"]
                scopes = params.get("scopes", [])
                try:
                    if context and hasattr(context, "token_manager"):
                        manager = context.token_manager
                        if manager:
                            server_config = context.server_registry.get_server_config(
                                server_name
                            )

                            token = await manager.get_access_token_if_present(
                                context=context,
                                server_name=server_name,
                                server_config=server_config,
                                scopes=scopes,
                                identity=identity,
                            )
                            if token:
                                return token
                except Exception:
                    # elicitation fallback below
                    pass

                # token is not present in the cache, perform the auth flow
                record = await _perform_auth_flow(context, params, scopes, session)

                # save in the token manager for next time
                try:
                    if context and hasattr(context, "token_manager"):
                        manager = context.token_manager
                        if manager:
                            server_config = context.server_registry.get_server_config(
                                server_name
                            )

                            token_data = {
                                "access_token": record.access_token,
                                "refresh_token": record.refresh_token,
                                "scopes": record.scopes,
                                "authorization_server": record.authorization_server,
                                "expires_at": record.expires_at,
                                "token_type": "Bearer",
                            }

                            await manager.store_user_token(
                                context=context,
                                user=identity,
                                server_name=server_name,
                                server_config=server_config,
                                token_data=token_data,
                            )
                except Exception:
                    pass

                return {"token_record": record.model_dump_json()}
            else:
                raise ValueError(f"unsupported method: {method}")

        async def _perform_auth_flow(context, params, scopes, session):
            from mcp.types import (
                ElicitRequest,
                ElicitRequestParams,
                ElicitResult,
            )

            class AuthToken(BaseModel):
                confirmation: str = Field(
                    description="Please press enter to confirm this message has been received"
                )

            flow_id = params["flow_id"]
            flow_timeout_seconds = params.get("flow_timeout_seconds")
            state = params["state"]
            token_endpoint = params["token_endpoint"]
            redirect_uri = params["redirect_uri"]
            client_id = params["client_id"]
            code_verifier = params["code_verifier"]
            resource = params.get("resource")
            scope_param = params.get("scope_param")
            extra_token_params = params.get("extra_token_params", {})
            client_secret = params.get("client_secret")
            issuer_str = params.get("issuer_str")
            authorization_server_url = params.get("authorization_server_url")
            callback_future = await callback_registry.create_handle(flow_id)
            req = ElicitRequest(
                method="elicitation/create",
                params=ElicitRequestParams(
                    message=params["message"] + "\n\n" + params["url"],
                    requestedSchema=AuthToken.model_json_schema(),
                ),
            )
            await session.send_request(request=req, result_type=ElicitResult)  # type: ignore[attr-defined]
            timeout = 300
            try:
                callback_data = await asyncio.wait_for(callback_future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise CallbackTimeoutError(
                    f"Timed out waiting for OAuth callback after {timeout} seconds"
                ) from exc
            try:
                if callback_data and callback_data.get("url"):
                    callback_data = _parse_callback_params(callback_data["url"])
                    if callback_future is not None:
                        await callback_registry.discard(flow_id)
                elif callback_data and callback_data.get("code"):
                    callback_data = callback_data
                    if callback_future is not None:
                        await callback_registry.discard(flow_id)
                elif callback_future is not None:
                    timeout = flow_timeout_seconds or 300
                    try:
                        callback_data = await asyncio.wait_for(
                            callback_future, timeout=timeout
                        )
                    except asyncio.TimeoutError as exc:
                        raise CallbackTimeoutError(
                            f"Timed out waiting for OAuth callback after {timeout} seconds"
                        ) from exc
                else:
                    raise AuthorizationDeclined(
                        "Authorization request was declined by the user"
                    )
            finally:
                if callback_future is not None:
                    await callback_registry.discard(flow_id)
            error = callback_data.get("error")
            if error:
                description = callback_data.get("error_description") or error
                raise OAuthFlowError(
                    f"Authorization server returned error: {description}"
                )
            returned_state = callback_data.get("state")
            if returned_state != state:
                raise OAuthFlowError("State mismatch detected in OAuth callback")
            authorization_code = callback_data.get("code")
            if not authorization_code:
                raise OAuthFlowError("Authorization callback did not include code")
            token_endpoint = str(token_endpoint)
            data: Dict[str, Any] = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
                "resource": resource,
            }
            if scope_param:
                data["scope"] = scope_param
            if extra_token_params:
                data.update(extra_token_params)
            auth = None
            if client_secret:
                data["client_secret"] = client_secret
            try:
                if context and hasattr(context, "token_manager"):
                    manager = context.token_manager
                    if manager:
                        http_client = manager._http_client
            except Exception:
                http_client = None
            if not http_client:
                http_client = httpx.AsyncClient(timeout=30.0)
            token_response = await http_client.post(
                token_endpoint,
                data=data,
                auth=auth,
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            try:
                callback_data = token_response.json()
            except JSONDecodeError:
                callback_data = _parse_callback_params("?" + token_response.text)
            access_token = callback_data.get("access_token")
            if not access_token:
                raise OAuthFlowError("Token endpoint response missing access_token")
            refresh_token = callback_data.get("refresh_token")
            expires_in = callback_data.get("expires_in")
            expires_at = None
            if isinstance(expires_in, (int, float)):
                expires_at = time.time() + float(expires_in)
            scope_from_payload = callback_data.get("scope")
            if isinstance(scope_from_payload, str) and scope_from_payload.strip():
                effective_scopes = tuple(scope_from_payload.split())
            else:
                effective_scopes = tuple(scopes)
            record = TokenRecord(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scopes=effective_scopes,
                token_type=str(callback_data.get("token_type", "Bearer")),
                resource=resource,
                authorization_server=issuer_str,
                metadata={
                    "raw": token_response.text,
                    "authorization_server_url": authorization_server_url,
                },
            )
            return record

        async def _try_session_request(
            session,
            method: str,
            params: dict,
            execution_id: str,
            context: Optional["Context"],
            log_prefix: str = "request",
            register_session: bool = False,
        ):
            """Try to handle a request via session, with optional registration."""
            try:
                identity = _get_identity_for_execution(execution_id)
            except Exception:
                identity = None

            try:
                # First try generic RPC passthrough
                result = await _handle_request_via_rpc(
                    session, method, params, execution_id, log_prefix
                )
                if result is not None:
                    if register_session:
                        try:
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=session,
                                identity=identity,
                                context=context,
                                session_id=getattr(context, "request_session_id", None),
                            )
                        except Exception:
                            pass
                    return result

                # Fallback to specific structured request handling
                result = await _handle_specific_request(
                    session, method, params, identity, context, log_prefix
                )
                if register_session:
                    try:
                        await _register_session(
                            run_id=execution_id,
                            execution_id=execution_id,
                            session=session,
                            identity=identity,
                            context=context,
                            session_id=getattr(context, "request_session_id", None),
                        )
                    except Exception:
                        pass
                return result
            except Exception as e:
                if "unsupported method" in str(e):
                    raise  # Re-raise unsupported method errors
                logger.warning(
                    f"[{log_prefix}] session delivery failed for execution_id={execution_id} method={method}: {e}"
                )
                raise

        @mcp_server.custom_route(
            "/internal/session/by-run/{execution_id}/request",
            methods=["POST"],
            include_in_schema=False,
        )
        async def _relay_request(request: Request):
            app = _get_attached_app(mcp_server)
            if app and app.context:
                app_context = app.context
            else:
                app_context = None

            body = await request.json()
            execution_id = request.path_params.get("execution_id")
            method = body.get("method")
            params = body.get("params") or {}
            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )
            effective_context = mapped_context or app_context

            # Check authentication
            auth_error = _check_gateway_auth(request)
            if auth_error:
                return auth_error

            # Try latest upstream session first
            latest_session = _get_fallback_upstream_session()
            if latest_session is not None:
                try:
                    ctx_token_latest: Token | None = None
                    if effective_context is not None:
                        ctx_token_latest = set_current_request_context(
                            effective_context
                        )
                    try:
                        result = await _try_session_request(
                            latest_session,
                            method,
                            params,
                            execution_id,
                            effective_context,
                            log_prefix="request",
                            register_session=True,
                        )
                    finally:
                        reset_current_request_context(ctx_token_latest)
                    return JSONResponse(result)
                except Exception as e_latest:
                    # Only log and continue to fallback if it's not an unsupported method error
                    if "unsupported method" not in str(e_latest):
                        logger.warning(
                            f"[request] latest session delivery failed for execution_id={execution_id} method={method}: {e_latest}"
                        )

            # Refresh mapping after any rebinding that may have occurred above
            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )
            effective_context = mapped_context or app_context

            # Fallback to mapped session
            session = await _get_session(execution_id)
            if not session:
                logger.warning(
                    f"[request] session_not_available for execution_id={execution_id}"
                )
                return JSONResponse({"error": "session_not_available"}, status_code=503)

            ctx_token_mapped: Token | None = None
            if effective_context is not None:
                ctx_token_mapped = set_current_request_context(effective_context)
            try:
                result = await _try_session_request(
                    session,
                    method,
                    params,
                    execution_id,
                    effective_context,
                    log_prefix="request",
                    register_session=False,
                )
                return JSONResponse(result)
            except Exception as e:
                if "unsupported method" in str(e):
                    return JSONResponse(
                        {"error": f"unsupported method: {method}"}, status_code=400
                    )
                try:
                    logger.error(
                        f"[request] error forwarding for execution_id={execution_id} method={method}: {e}"
                    )
                except Exception:
                    pass
                return JSONResponse({"error": str(e)}, status_code=500)
            finally:
                reset_current_request_context(ctx_token_mapped)

        @mcp_server.custom_route(
            "/internal/session/by-run/{workflow_id}/{execution_id}/async-request",
            methods=["POST"],
            include_in_schema=False,
        )
        async def _async_relay_request(request: Request):
            body = await request.json()
            execution_id = request.path_params.get("execution_id")
            workflow_id = request.path_params.get("workflow_id")
            method = body.get("method")
            params = body.get("params") or {}
            signal_name = body.get("signal_name")

            # Check authentication
            auth_error = _check_gateway_auth(request)
            if auth_error:
                return auth_error

            try:
                logger.info(
                    f"[async-request] incoming execution_id={execution_id} method={method}"
                )
            except Exception:
                pass

            if method != "sampling/createMessage" and method != "elicitation/create":
                logger.error(f"async not supported for method {method}")
                return JSONResponse(
                    {"error": f"async not supported for method {method}"},
                    status_code=405,
                )

            if not signal_name:
                return JSONResponse({"error": "missing_signal_name"}, status_code=400)

            # Create background task to handle the request and signal the workflow
            async def _handle_async_request_task():
                app = _get_attached_app(mcp_server)
                if app and app.context:
                    app_context = app.context
                else:
                    app_context = None

                mapped_context = (
                    _get_context_for_execution(execution_id) if execution_id else None
                )
                effective_context = mapped_context or app_context
                task_token: Token | None = None
                if effective_context is not None:
                    task_token = set_current_request_context(effective_context)

                try:
                    result = None

                    # Try latest upstream session first
                    latest_session = _get_fallback_upstream_session()
                    if latest_session is not None:
                        try:
                            ctx_token_latest: Token | None = None
                            if effective_context is not None:
                                ctx_token_latest = set_current_request_context(
                                    effective_context
                                )
                            try:
                                result = await _try_session_request(
                                    latest_session,
                                    method,
                                    params,
                                    execution_id,
                                    effective_context,
                                    log_prefix="async-request",
                                    register_session=True,
                                )
                            finally:
                                reset_current_request_context(ctx_token_latest)
                        except Exception as e_latest:
                            logger.warning(
                                f"[async-request] latest session delivery failed for execution_id={execution_id} method={method}: {e_latest}"
                            )

                    # Fallback to mapped session if latest session failed
                    if result is None:
                        session = await _get_session(execution_id)
                        if session:
                            try:
                                ctx_token_mapped: Token | None = None
                                if mapped_context is not None:
                                    ctx_token_mapped = set_current_request_context(
                                        mapped_context
                                    )
                                try:
                                    result = await _try_session_request(
                                        session,
                                        method,
                                        params,
                                        execution_id,
                                        mapped_context or app_context,
                                        log_prefix="async-request",
                                        register_session=False,
                                    )
                                finally:
                                    reset_current_request_context(ctx_token_mapped)
                            except Exception as e:
                                logger.error(
                                    f"[async-request] error forwarding for execution_id={execution_id} method={method}: {e}"
                                )
                                result = {"error": str(e)}
                        else:
                            logger.warning(
                                f"[async-request] session_not_available for execution_id={execution_id}"
                            )
                            result = {"error": "session_not_available"}

                    # Signal the workflow with the result using method-specific signal
                    try:
                        # Try to get Temporal client from the app context
                        if app_context and hasattr(app_context, "executor"):
                            executor = app_context.executor
                            if hasattr(executor, "client"):
                                client = executor.client
                                # Find the workflow using execution_id as both workflow_id and run_id
                                try:
                                    workflow_handle = client.get_workflow_handle(
                                        workflow_id=workflow_id, run_id=execution_id
                                    )

                                    await workflow_handle.signal(signal_name, result)
                                    logger.info(
                                        f"[async-request] signaled workflow {execution_id} "
                                        f"with {method} result using signal"
                                    )
                                except Exception as signal_error:
                                    logger.warning(
                                        f"[async-request] failed to signal workflow {execution_id}:"
                                        f" {signal_error}"
                                    )
                    except Exception as e:
                        logger.error(f"[async-request] failed to signal workflow: {e}")

                except Exception as e:
                    logger.error(f"[async-request] background task error: {e}")
                finally:
                    reset_current_request_context(task_token)

            # Start the background task
            asyncio.create_task(_handle_async_request_task())

            # Return immediately with 200 status to indicate request was received
            return JSONResponse(
                {
                    "status": "received",
                    "execution_id": execution_id,
                    "method": method,
                    "signal_name": signal_name,
                }
            )

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

            # Check authentication
            auth_error = _check_gateway_auth(request)
            if auth_error:
                return auth_error

            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )

            # Prefer latest upstream session first
            latest_session = _get_fallback_upstream_session()
            if latest_session is not None:
                try:
                    latest_token: Token | None = None
                    if mapped_context is not None:
                        latest_token = set_current_request_context(mapped_context)
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
                    finally:
                        reset_current_request_context(latest_token)
                    logger.debug(
                        f"[log] delivered via latest session_id={id(latest_session)} level={level} ns={namespace}"
                    )
                    try:
                        identity = _get_identity_for_execution(execution_id)
                        existing_context = _get_context_for_execution(execution_id)
                        await _register_session(
                            run_id=execution_id,
                            execution_id=execution_id,
                            session=latest_session,
                            identity=identity,
                            context=existing_context,
                            session_id=getattr(
                                existing_context, "request_session_id", None
                            ),
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
                mapped_token: Token | None = None
                if mapped_context is not None:
                    mapped_token = set_current_request_context(mapped_context)
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
                finally:
                    reset_current_request_context(mapped_token)
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

            # Check authentication
            auth_error = _check_gateway_auth(request)
            if auth_error:
                return auth_error

            app_obj = _get_attached_app(mcp_server)
            app_context = getattr(app_obj, "context", None) if app_obj else None
            mapped_context = (
                _get_context_for_execution(execution_id) if execution_id else None
            )
            effective_context = mapped_context or app_context

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
                        latest_token: Token | None = None
                        if effective_context is not None:
                            latest_token = set_current_request_context(
                                effective_context
                            )
                        try:
                            await latest_session.send_log_message(  # type: ignore[attr-defined]
                                level="info",  # type: ignore[arg-type]
                                data=payload,
                                logger="mcp_agent.human",
                            )
                        finally:
                            reset_current_request_context(latest_token)
                        try:
                            identity = _get_identity_for_execution(execution_id)
                            if identity is None:
                                identity = _session_identity_from_value(
                                    metadata.get("session_id")
                                    or metadata.get("sessionId")
                                )
                            existing_context = _get_context_for_execution(execution_id)
                            session_key = metadata.get("session_id") or metadata.get(
                                "sessionId"
                            )
                            await _register_session(
                                run_id=execution_id,
                                execution_id=execution_id,
                                session=latest_session,
                                identity=identity,
                                context=existing_context,
                                session_id=session_key
                                or getattr(
                                    existing_context, "request_session_id", None
                                ),
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
                mapped_context = (
                    _get_context_for_execution(execution_id) if execution_id else None
                )
                effective_context = mapped_context or app_context
                session = await _get_session(execution_id)
                if not session:
                    return JSONResponse(
                        {"error": "session_not_available"}, status_code=503
                    )
                mapped_token: Token | None = None
                if effective_context is not None:
                    mapped_token = set_current_request_context(effective_context)
                try:
                    await session.send_log_message(
                        level="info",  # type: ignore[arg-type]
                        data=payload,
                        logger="mcp_agent.human",
                    )
                finally:
                    reset_current_request_context(mapped_token)
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
        if "icons" not in kwargs and app._icons:
            kwargs["icons"] = app._icons
        if "auth" not in kwargs and effective_auth_settings is not None:
            kwargs["auth"] = effective_auth_settings
        if "token_verifier" not in kwargs and token_verifier is not None:
            kwargs["token_verifier"] = token_verifier
            owns_token_verifier = True

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
                ctx_obj: MCPContext | None = None
                try:
                    ctx_obj = mcp.get_context() if hasattr(mcp, "get_context") else None
                except Exception:
                    ctx_obj = None

                bound_ctx: Context | None = None
                token: Token | None = None
                if ctx_obj is not None:
                    try:
                        bound_ctx, token = _enter_request_context(ctx_obj)
                    except Exception:
                        bound_ctx, token = None, None

                try:
                    session_id = (
                        getattr(bound_ctx, "request_session_id", None)
                        if bound_ctx is not None
                        else None
                    )
                    if session_id:
                        LoggingConfig.set_session_min_level(session_id, level)
                    else:
                        LoggingConfig.set_min_level(level)
                except Exception:
                    pass
                finally:
                    _exit_request_context(bound_ctx, token)
    except Exception:
        # If handler registration fails, continue without dynamic level updates
        pass

    # region Workflow Tools

    @mcp.tool(name="workflows-list", icons=[phetch])
    def list_workflows(ctx: MCPContext) -> Dict[str, Dict[str, Any]]:
        """
        List all available workflow types with their detailed information.
        Returns information about each workflow type including name, description, and parameters.
        This helps in making an informed decision about which workflow to run.
        """
        bound_ctx, token = _enter_request_context(ctx)
        try:
            result: Dict[str, Dict[str, Any]] = {}
            workflows, _ = _resolve_workflows_and_context_safe(ctx, bound_ctx)
            workflows = workflows or {}
        finally:
            _exit_request_context(bound_ctx, token)
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

    @mcp.tool(name="workflows-runs-list", icons=[phetch])
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
        bound_ctx, token = _enter_request_context(ctx)
        try:
            server_context = getattr(
                ctx.request_context, "lifespan_context", None
            ) or _get_attached_server_context(ctx.fastmcp)
            if server_context is None or not hasattr(
                server_context, "workflow_registry"
            ):
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
        finally:
            _exit_request_context(bound_ctx, token)

    @mcp.tool(name="workflows-run", icons=[phetch])
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
        bound_ctx, token = _enter_request_context(ctx)
        try:
            return await _workflow_run(
                ctx, workflow_name, run_parameters, bound_context=bound_ctx, **kwargs
            )
        finally:
            _exit_request_context(bound_ctx, token)

    @mcp.tool(name="workflows-get_status", icons=[phetch])
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
        bound_ctx, token = _enter_request_context(ctx)
        try:
            try:
                sess = getattr(ctx, "session", None)
                if sess and run_id:
                    exec_id = _RUN_EXECUTION_ID_REGISTRY.get(run_id, run_id)
                    app_obj = _get_attached_app(ctx.fastmcp)
                    app_ctx = getattr(app_obj, "context", None) if app_obj else None
                    identity = _resolve_identity_for_request(ctx, app_ctx, exec_id)
                    await _register_session(
                        run_id=run_id,
                        execution_id=exec_id,
                        session=sess,
                        identity=identity,
                        context=bound_ctx,
                        session_id=getattr(bound_ctx, "request_session_id", None),
                    )
            except Exception:
                pass
            return await _workflow_status(
                ctx,
                run_id=run_id,
                workflow_id=workflow_id,
                bound_context=bound_ctx,
            )
        finally:
            _exit_request_context(bound_ctx, token)

    @mcp.tool(name="workflows-resume", icons=[phetch])
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
        bound_ctx, token = _enter_request_context(ctx)
        try:
            try:
                sess = getattr(ctx, "session", None)
                if sess and run_id:
                    exec_id = _RUN_EXECUTION_ID_REGISTRY.get(run_id, run_id)
                    app_obj = _get_attached_app(ctx.fastmcp)
                    app_ctx = getattr(app_obj, "context", None) if app_obj else None
                    identity = _resolve_identity_for_request(ctx, app_ctx, exec_id)
                    await _register_session(
                        run_id=run_id,
                        execution_id=exec_id,
                        session=sess,
                        identity=identity,
                        context=bound_ctx,
                        session_id=getattr(bound_ctx, "request_session_id", None),
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
        finally:
            _exit_request_context(bound_ctx, token)

    @mcp.tool(name="workflows-cancel", icons=[phetch])
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
        bound_ctx, token = _enter_request_context(ctx)
        try:
            try:
                sess = getattr(ctx, "session", None)
                if sess and run_id:
                    exec_id = _RUN_EXECUTION_ID_REGISTRY.get(run_id, run_id)
                    app_obj = _get_attached_app(ctx.fastmcp)
                    app_ctx = getattr(app_obj, "context", None) if app_obj else None
                    identity = _resolve_identity_for_request(ctx, app_ctx, exec_id)
                    await _register_session(
                        run_id=run_id,
                        execution_id=exec_id,
                        session=sess,
                        identity=identity,
                        context=bound_ctx,
                        session_id=getattr(bound_ctx, "request_session_id", None),
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
        finally:
            _exit_request_context(bound_ctx, token)

    @mcp.tool(name="workflows-store-credentials")
    async def workflow_store_credentials(
        ctx: MCPContext, workflow_name: str, tokens: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Store OAuth tokens for a workflow to use with MCP servers.

        Persisting tokens ahead of time lets workflows authenticate with external services
        without needing an interactive OAuth flow at execution time.

        Args:
            workflow_name: The name of the workflow that will use these tokens.
            tokens: List of OAuth token objects, each containing:
                - access_token (str): The OAuth access token
                - refresh_token (str, optional): The OAuth refresh token
                - server_name (str): Name/identifier of the MCP server
                - scopes (List[str], optional): List of OAuth scopes
                - expires_at (float, optional): Token expiration timestamp
                - authorization_server (str, optional): Authorization server URL

        Returns:
            Dictionary with success status and count of stored tokens.
        """
        bound_ctx, token = _enter_request_context(ctx)
        try:
            workflows_dict, app_context = _resolve_workflows_and_context_safe(
                ctx, bound_ctx
            )
            if not workflows_dict or not app_context:
                raise ToolError("Server context not available for MCPApp Server.")

            if workflow_name not in workflows_dict:
                raise ToolError(f"Workflow '{workflow_name}' not found.")

            if not app_context.token_manager:
                raise ToolError("OAuth token manager not available.")

            identity = _resolve_identity_for_request(ctx, app_context)

            if not tokens:
                raise ToolError("At least one token must be provided.")

            stored_count = 0
            errors = []

            for i, token_data in enumerate(tokens):
                try:
                    if not isinstance(token_data, dict):
                        errors.append(f"Token {i}: must be a dictionary")
                        continue

                    access_token = token_data.get("access_token")
                    server_name = token_data.get("server_name")

                    if not access_token:
                        errors.append(
                            f"Token {i}: missing required 'access_token' field"
                        )
                        continue

                    if not server_name:
                        errors.append(
                            f"Token {i}: missing required 'server_name' field"
                        )
                        continue

                    server_config = app_context.server_registry.registry.get(
                        server_name
                    )
                    if not server_config:
                        errors.append(
                            f"Token {i}: server '{server_name}' not recognized"
                        )
                        continue

                    await app_context.token_manager.store_user_token(
                        context=app_context,
                        user=identity,
                        server_name=server_name,
                        server_config=server_config,
                        token_data=token_data,
                        workflow_name=workflow_name,
                    )
                    stored_count += 1
                except Exception as e:
                    errors.append(f"Token {i}: {str(e)}")
                    logger.error(
                        f"Error storing token {i} for workflow '{workflow_name}': {e}"
                    )

            if errors and stored_count == 0:
                raise ToolError(
                    f"Failed to store any tokens. Errors: {'; '.join(errors)}"
                )

            result = {
                "success": True,
                "workflow_name": workflow_name,
                "stored_tokens": stored_count,
                "total_tokens": len(tokens),
            }

            if errors:
                result["errors"] = errors
                result["partial_success"] = True

            logger.info(
                f"Pre-authorization completed for workflow '{workflow_name}': "
                f"{stored_count}/{len(tokens)} tokens stored"
            )

            return result

        except Exception as e:
            logger.error(
                f"Error in workflow pre-authorization for '{workflow_name}': {e}"
            )
            raise ToolError(f"Failed to store tokens: {str(e)}")
        finally:
            _exit_request_context(bound_ctx, token)

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
    import typing as _typing

    try:
        from mcp.server.fastmcp import Context as _Ctx
    except Exception:
        _Ctx = None  # type: ignore

    def _annotation_is_fast_ctx(annotation) -> bool:
        if _Ctx is None or annotation is inspect._empty:
            return False
        if annotation is _Ctx:
            return True
        if inspect.isclass(annotation):
            try:
                if issubclass(annotation, _Ctx):  # type: ignore[misc]
                    return True
            except TypeError:
                pass
        try:
            origin = _typing.get_origin(annotation)
            if origin is not None:
                return any(
                    _annotation_is_fast_ctx(arg) for arg in _typing.get_args(annotation)
                )
        except Exception:
            pass
        try:
            return "fastmcp" in str(annotation)
        except Exception:
            return False

    def _detect_context_param(signature: inspect.Signature) -> str | None:
        for param in signature.parameters.values():
            if param.name == "app_ctx":
                continue
            if _annotation_is_fast_ctx(param.annotation):
                return param.name
            if param.annotation is inspect._empty and param.name in {"ctx", "context"}:
                return param.name
        return None

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
        title = decl.get("title")
        annotations = decl.get("annotations")
        icons = decl.get("icons")
        meta = decl.get("meta")

        # Bind per-iteration values to avoid late-binding closure bugs
        name_local = name
        wname_local = workflow_name

        if mode == "sync" and fn is not None:
            sig = inspect.signature(fn)
            return_ann = sig.return_annotation

            def _make_wrapper(bound_wname: str):
                async def _wrapper(**kwargs):
                    ctx: MCPContext = kwargs.pop("__context__")
                    bound_ctx, token = _enter_request_context(ctx)
                    try:
                        result_ids = await _workflow_run(
                            ctx,
                            bound_wname,
                            kwargs,
                            bound_context=bound_ctx,
                        )
                        run_id = result_ids["run_id"]
                        result = await _wait_for_completion(ctx, run_id)
                    finally:
                        _exit_request_context(bound_ctx, token)
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

            existing_ctx_param = _detect_context_param(sig)
            ctx_param_name = existing_ctx_param or "ctx"

            if _Ctx is not None:
                ann[ctx_param_name] = _Ctx
            ann["return"] = getattr(fn, "__annotations__", {}).get("return", return_ann)
            _wrapper.__annotations__ = ann
            _wrapper.__name__ = name_local
            _wrapper.__doc__ = description or (fn.__doc__ or "")

            params = [p for p in sig.parameters.values() if p.name != "app_ctx"]
            if existing_ctx_param is None:
                ctx_param = inspect.Parameter(
                    ctx_param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=_Ctx,
                )
                signature_params = params + [ctx_param]
            else:
                signature_params = params

            _wrapper.__signature__ = inspect.Signature(
                parameters=signature_params, return_annotation=return_ann
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
                title=title,
                description=description or (fn.__doc__ or ""),
                annotations=annotations,
                icons=icons,
                meta=meta,
                structured_output=structured_output,
            )
            registered.add(name_local)

        elif mode == "async":
            # Use the declared name as the async run endpoint
            run_tool_name = f"{name_local}"

            if run_tool_name not in registered:
                # Build a wrapper mirroring original function params (excluding app_ctx/ctx)
                def _make_async_wrapper(bound_wname: str):
                    async def _async_wrapper(**kwargs):
                        ctx: MCPContext = kwargs.pop("__context__")
                        bound_ctx, token = _enter_request_context(ctx)
                        try:
                            return await _workflow_run(
                                ctx,
                                bound_wname,
                                kwargs,
                                bound_context=bound_ctx,
                            )
                        finally:
                            _exit_request_context(bound_ctx, token)

                    return _async_wrapper

                _async_wrapper = _make_async_wrapper(wname_local)

                # Mirror original signature and annotations similar to sync path
                ann = dict(getattr(fn, "__annotations__", {}))
                ann.pop("app_ctx", None)

                try:
                    sig_async = inspect.signature(fn)
                except Exception:
                    sig_async = None
                existing_ctx_param = (
                    _detect_context_param(sig_async) if sig_async else None
                )

                ctx_param_name = existing_ctx_param or "ctx"
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
                if sig_async is not None:
                    for p in sig_async.parameters.values():
                        if p.name == "app_ctx":
                            continue
                        if existing_ctx_param is None and (
                            _annotation_is_fast_ctx(p.annotation)
                            or p.name in ("ctx", "context")
                        ):
                            continue
                        params.append(p)

                # Append kw-only context param
                if existing_ctx_param is None:
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
                    signature_params = params + [ctx_param]
                else:
                    signature_params = params

                _async_wrapper.__signature__ = inspect.Signature(
                    parameters=signature_params, return_annotation=ann.get("return")
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
                    title=title,
                    description=full_desc,
                    annotations=annotations,
                    icons=icons,
                    meta=meta,
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
        icons=[phetch],
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
        bound_ctx, token = _enter_request_context(ctx)
        try:
            return await _workflow_run(
                ctx, workflow_name, run_parameters, bound_context=bound_ctx
            )
        finally:
            _exit_request_context(bound_ctx, token)


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
    *,
    bound_context: Optional["Context"] = None,
    **kwargs: Any,
) -> Dict[str, str]:
    # Use Temporal run_id as the routing key for gateway callbacks.
    # We don't have it until after the workflow is started; we'll register mapping post-start.

    # Resolve workflows and app context irrespective of startup mode
    # This now returns a context with upstream_session already set
    workflows_dict, app_context = _resolve_workflows_and_context_safe(
        ctx, bound_context
    )
    if not workflows_dict or not app_context:
        raise ToolError("Server context not available for MCPApp Server.")

    # Bind the app context to this FastMCP request so request-scoped methods
    # (client_id, request_id, log/progress/resource reads) work seamlessly.
    bound_app_context = bound_context or app_context
    if bound_app_context is None:
        raise ToolError("Unable to resolve request context for workflow execution.")

    if bound_context is None:
        try:
            request_ctx = getattr(ctx, "request_context", None)
        except Exception:
            request_ctx = None
        if request_ctx is not None and hasattr(app_context, "bind_request"):
            try:
                bound_app_context = app_context.bind_request(
                    request_ctx,
                    getattr(ctx, "fastmcp", None),
                )
                if (
                    getattr(bound_app_context, "upstream_session", None) is None
                    and getattr(app_context, "upstream_session", None) is not None
                ):
                    bound_app_context.upstream_session = app_context.upstream_session
            except Exception:
                bound_app_context = app_context
        else:
            bound_app_context = app_context

    # Expose the per-request bound context on the FastMCP context for adapters
    try:
        object.__setattr__(ctx, "bound_app_context", bound_app_context)
    except Exception:
        pass

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

            _get_logger(f"mcp_agent.{app.name}", context=bound_app_context)
    except Exception:
        pass

    # Create and initialize the workflow instance using the factory method
    try:
        # Create workflow instance with context that has upstream_session
        workflow = await workflow_cls.create(
            name=workflow_name, context=bound_app_context
        )
        try:
            setattr(workflow, "_mcp_request_context", ctx)
        except Exception:
            pass

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
            identity = _resolve_identity_for_request(ctx, app_context, execution_id)
            await _register_session(
                run_id=execution.run_id,
                execution_id=execution_id,
                session=getattr(ctx, "session", None),
                identity=identity,
                context=bound_app_context,
                session_id=getattr(bound_app_context, "request_session_id", None),
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
    ctx: MCPContext,
    run_id: str | None = None,
    workflow_id: str | None = None,
    *,
    bound_context: Optional["Context"] = None,
) -> Dict[str, Any]:
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


def _parse_callback_params(url: str) -> Dict[str, str]:
    parsed = urlparse(url)
    params = {}
    params.update({k: v[-1] for k, v in parse_qs(parsed.query).items()})
    if parsed.fragment:
        params.update({k: v[-1] for k, v in parse_qs(parsed.fragment).items()})
    return params
