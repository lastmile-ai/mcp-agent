"""Utilities for propagating authenticated user identity across async tasks."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from mcp_agent.oauth.identity import OAuthUserIdentity

_identity_var: ContextVar[OAuthUserIdentity | None] = ContextVar(
    "mcp_agent_current_identity", default=None
)
_session_var: ContextVar[str | None] = ContextVar(
    "mcp_agent_current_session_id", default=None
)


def get_current_identity() -> OAuthUserIdentity | None:
    """Return the identity bound to the current task, if any."""
    return _identity_var.get()


def get_current_session_id() -> str | None:
    """Return the session id bound to the current task, if any."""
    return _session_var.get()


def push_identity(
    identity: OAuthUserIdentity | None, session_id: str | None = None
) -> tuple[Token, Token]:
    """Bind identity/session to the current task and return reset tokens."""
    identity_token = _identity_var.set(identity)
    session_token = _session_var.set(session_id)
    return identity_token, session_token


def reset_identity(tokens: tuple[Token, Token]) -> None:
    """Reset identity/session using previously returned tokens."""
    identity_token, session_token = tokens
    _identity_var.reset(identity_token)
    _session_var.reset(session_token)


@contextmanager
def identity_scope(
    identity: OAuthUserIdentity | None, session_id: str | None = None
) -> Iterator[None]:
    """Context manager that temporarily binds identity/session."""
    tokens = push_identity(identity, session_id)
    try:
        yield
    finally:
        reset_identity(tokens)
