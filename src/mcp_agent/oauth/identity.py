"""Utilities for representing authenticated MCP users."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from .access_token import MCPAccessToken


@dataclass(frozen=True)
class OAuthUserIdentity:
    """Canonical identifier for an authenticated user within MCP Agent."""

    provider: str
    subject: str
    email: str | None = None
    claims: Dict[str, Any] | None = None

    @property
    def cache_key(self) -> str:
        """Return a deterministic cache key for token storage."""
        return f"{self.provider}:{self.subject}"

    @classmethod
    def from_access_token(
        cls, token: MCPAccessToken | None
    ) -> "OAuthUserIdentity" | None:
        """Build an identity from an enriched access token."""
        if token is None:
            return None
        raw_subject = token.subject
        if not isinstance(raw_subject, str) or not raw_subject.strip():
            raw_subject = _claim(token, "sub")
        if not isinstance(raw_subject, str) or not raw_subject.strip():
            return None
        subject = raw_subject.strip()
        raw_provider = token.issuer or _claim(token, "iss")
        provider = (
            raw_provider.strip()
            if isinstance(raw_provider, str) and raw_provider.strip()
            else "unknown"
        )
        raw_email = (
            token.email or _claim(token, "email") or _claim(token, "preferred_username")
        )
        email = (
            raw_email.strip()
            if isinstance(raw_email, str) and raw_email.strip()
            else None
        )
        claims = token.claims or {}
        return cls(provider=provider, subject=subject, email=email, claims=claims)


def _claim(token: MCPAccessToken, key: str) -> Any | None:
    if not token.claims:
        return None
    return token.claims.get(key)


DEFAULT_PRECONFIGURED_IDENTITY = OAuthUserIdentity(
    provider="mcp-agent",
    subject="preconfigured-tokens",
    claims={
        "token_source": "synthetic",
        "description": "Synthetic identity used when no user/session is available",
    },
)


def is_authenticated_identity(identity: OAuthUserIdentity | None) -> bool:
    """Return True if identity represents an authenticated user rather than a synthetic or session fallback."""
    if identity is None or identity == DEFAULT_PRECONFIGURED_IDENTITY:
        return False
    if identity.provider == "mcp-session":
        return False
    return (
        isinstance(identity.subject, str)
        and bool(identity.subject.strip())
        and isinstance(identity.provider, str)
        and bool(identity.provider.strip())
    )


def is_authorization_enabled(context: Any | None) -> bool:
    """Return True if MCP server authorization is enabled on the given context."""
    if context is None:
        return False
    config = getattr(context, "config", None)
    auth_cfg = getattr(config, "authorization", None)
    return bool(auth_cfg and getattr(auth_cfg, "enabled", False))


def resolve_identity_from_auth_context() -> Tuple[bool, OAuthUserIdentity | None]:
    """Extract (has_authenticated_user, identity) from the active MCP auth contextvar."""
    try:
        from mcp.server.auth.middleware.auth_context import (
            AuthenticatedUser,
            auth_context_var,
        )

        auth_user = auth_context_var.get()
    except Exception:
        return False, None

    if not isinstance(auth_user, AuthenticatedUser):
        return False, None

    identity: OAuthUserIdentity | None = None
    access_token = getattr(auth_user, "access_token", None)
    if access_token is not None:
        try:
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

    if not is_authenticated_identity(identity):
        return True, None

    return True, identity


def session_identity(session_id: str | None) -> OAuthUserIdentity | None:
    """Build a deterministic identity for an unauthenticated MCP session."""
    if not session_id or not str(session_id).strip():
        return None
    return OAuthUserIdentity(
        provider="mcp-session",
        subject=str(session_id).strip(),
        claims={"token_source": "session"},
    )
