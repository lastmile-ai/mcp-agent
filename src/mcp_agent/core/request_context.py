"""
Helpers for managing per-request execution context without introducing circular imports.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from mcp_agent.core.context import Context


_CURRENT_REQUEST_CONTEXT: ContextVar[Optional["Context"]] = ContextVar(
    "mcp_agent_current_request_context", default=None
)


def set_current_request_context(ctx: Optional["Context"]) -> Token:
    """Bind the given context to the current execution context."""
    return _CURRENT_REQUEST_CONTEXT.set(ctx)


def reset_current_request_context(token: Token | None) -> None:
    """Reset the request context to a previous state."""
    if token is None:
        return
    try:
        _CURRENT_REQUEST_CONTEXT.reset(token)
    except Exception:
        pass


def get_current_request_context() -> Optional["Context"]:
    """Return the currently bound request-scoped context, if any."""
    try:
        return _CURRENT_REQUEST_CONTEXT.get()
    except LookupError:
        return None
