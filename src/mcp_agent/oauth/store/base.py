"""Abstract token store definition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from ..records import TokenRecord


@dataclass(frozen=True)
class TokenStoreKey:
    """Uniquely identifies a cached token."""

    user_key: str
    resource: str
    authorization_server: str | None
    scope_fingerprint: str


def scope_fingerprint(scopes: Iterable[str]) -> str:
    """Return a deterministic fingerprint for a scope list."""
    return " ".join(sorted({scope.strip() for scope in scopes if scope}))


class TokenStore(Protocol):
    """Persistence interface for OAuth tokens."""

    async def get(self, key: TokenStoreKey) -> TokenRecord | None: ...

    async def set(self, key: TokenStoreKey, record: TokenRecord) -> None: ...

    async def delete(self, key: TokenStoreKey) -> None: ...
