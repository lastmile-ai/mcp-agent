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
    audiences: List[str] | None = None

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

        # Enhanced audience extraction for RFC 9068 compliance
        audiences = _extract_all_audiences(payload)
        audience_value = audiences[0] if audiences else None
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
            audiences=audiences,
            claims=payload,
        )

    def is_expired(self, *, leeway_seconds: int = 0) -> bool:
        """Return True if token is expired considering optional leeway."""
        if self.expires_at is None:
            return False
        now = datetime.now(tz=timezone.utc).timestamp()
        return now >= (self.expires_at - leeway_seconds)

    def validate_audience(self, expected_audiences: List[str]) -> bool:
        """Validate this token's audience claims against expected values per RFC 9068."""
        if not self.audiences:
            return False
        if not expected_audiences:
            return False

        return bool(set(expected_audiences).intersection(set(self.audiences)))


def _extract_all_audiences(payload: Dict[str, Any]) -> List[str]:
    """Extract all audience values from token payload per RFC 9068."""
    audiences = []

    # Extract from 'aud' claim
    aud_claim = payload.get("aud")
    if aud_claim:
        if isinstance(aud_claim, str):
            audiences.append(aud_claim)
        elif isinstance(aud_claim, (list, tuple)):
            audiences.extend([str(aud) for aud in aud_claim if aud])

    # Extract from 'resource' claim (OAuth 2.0 resource indicators)
    resource_claim = payload.get("resource")
    if resource_claim:
        if isinstance(resource_claim, str):
            audiences.append(resource_claim)
        elif isinstance(resource_claim, (list, tuple)):
            audiences.extend([str(res) for res in resource_claim if res])

    return list(set(audiences))  # Remove duplicates


def _first_non_empty(*values: Any) -> Any | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        return value
    return None
