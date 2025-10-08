"""Utilities for representing authenticated MCP users."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

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
        subject = token.subject or _claim(token, "sub")
        if not subject:
            return None
        provider = token.issuer or _claim(token, "iss") or "unknown"
        email = (
            token.email or _claim(token, "email") or _claim(token, "preferred_username")
        )
        claims = token.claims or {}
        return cls(provider=provider, subject=subject, email=email, claims=claims)


def _claim(token: MCPAccessToken, key: str) -> Any | None:
    if not token.claims:
        return None
    return token.claims.get(key)


DEFAULT_PRECONFIGURED_IDENTITY = OAuthUserIdentity(
    provider="mcp-agent", subject="preconfigured-tokens"
)
