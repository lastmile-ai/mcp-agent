"""Extended access token model for MCP Agent authorization flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from mcp.server.auth.provider import AccessToken


class MCPAccessToken(AccessToken):
    """Access token enriched with identity and claim metadata."""

    subject: str | None = None
    email: str | None = None
    issuer: str | None = None
    resource_indicator: str | None = None
    claims: Dict[str, Any] | None = None

    @classmethod
    def from_introspection(
        cls,
        token: str,
        payload: Dict[str, Any],
        *,
        resource_hint: str | None = None,
    ) -> "MCPAccessToken":
        """Build an access token instance from an OAuth 2.0 introspection response."""
        client_id = _first_non_empty(
            payload.get("client_id"),
            payload.get("clientId"),
            payload.get("cid"),
        )
        scope_value = payload.get("scope") or payload.get("scp")
        if isinstance(scope_value, str):
            scopes: List[str] = [s for s in scope_value.split() if s]
        elif isinstance(scope_value, Iterable):
            scopes = [str(item) for item in scope_value]
        else:
            scopes = []

        audience = payload.get("resource") or payload.get("aud")
        if isinstance(audience, (list, tuple)):
            audience_value = _first_non_empty(*audience)
        else:
            audience_value = audience

        resource = resource_hint or audience_value

        expires_at = payload.get("exp")

        return cls(
            token=token,
            client_id=str(client_id) if client_id is not None else "",
            scopes=scopes,
            expires_at=expires_at,
            resource=resource,
            subject=_first_non_empty(payload.get("sub"), payload.get("subject")),
            email=_first_non_empty(
                payload.get("email"), payload.get("preferred_username")
            ),
            issuer=payload.get("iss"),
            resource_indicator=resource,
            claims=payload,
        )

    def is_expired(self, *, leeway_seconds: int = 0) -> bool:
        """Return True if token is expired considering optional leeway."""
        if self.expires_at is None:
            return False
        now = datetime.now(tz=timezone.utc).timestamp()
        return now >= (self.expires_at - leeway_seconds)


def _first_non_empty(*values: Any) -> Any | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        return value
    return None
