"""Placeholder for context prefetch helpers."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


async def prefetch_context(coro_factory: Callable[[], Awaitable[object]]) -> None:
    """Kick off a background coroutine that resolves eagerly.

    The actual product uses sophisticated heuristics; here we merely await the
    provided coroutine factory and ignore failures.
    """

    try:
        await coro_factory()
    except Exception:
        # Prefetch is a best-effort optimisation; suppress the error.
        return


__all__ = ["prefetch_context"]
