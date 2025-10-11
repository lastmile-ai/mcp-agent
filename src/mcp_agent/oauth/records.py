"""Shared record types for OAuth token management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from pydantic import BaseModel, Field


class TokenRecord(BaseModel):
    """Persisted token bundle for a user/resource/authorization server combination."""

    access_token: str
    refresh_token: str | None = None
    scopes: Tuple[str, ...] = ()
    expires_at: float | None = None
    token_type: str = "Bearer"
    resource: str | None = None
    authorization_server: str | None = None
    obtained_at: float = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc).timestamp()
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_expired(self, *, leeway_seconds: int = 0) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.now(tz=timezone.utc).timestamp()
        return now >= (self.expires_at - leeway_seconds)

    def with_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at: float | None,
    ) -> "TokenRecord":
        return self.model_copy(
            update={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "obtained_at": datetime.now(tz=timezone.utc).timestamp(),
            }
        )
