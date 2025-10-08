"""Token store implementations."""

from .base import TokenStore, TokenStoreKey, scope_fingerprint
from .in_memory import InMemoryTokenStore

__all__ = [
    "TokenStore",
    "TokenStoreKey",
    "scope_fingerprint",
    "InMemoryTokenStore",
]

try:  # Optional dependency
    from .redis import RedisTokenStore
except ImportError:  # pragma: no cover - redis extra not installed
    RedisTokenStore = None  # type: ignore[assignment]
else:
    __all__.append("RedisTokenStore")
