from contextlib import contextmanager
from typing import Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class ContextDependent:
    """
    Mixin class for components that need context access.
    Provides both global fallback and instance-specific context support.
    """

    def __init__(self, context: Optional["Context"] = None, **kwargs):
        self._context = context
        super().__init__(**kwargs)

    @property
    def context(self) -> "Context":
        """
        Get context, with graceful fallback to global context if needed.
        Raises clear error if no context is available.
        """
        # First try instance context
        if self._context is not None:
            return self._context

        try:
            # Fall back to global context if available
            from mcp_agent.core.context import get_current_context

            return get_current_context()
        except Exception as e:
            raise RuntimeError(
                f"No context available for {self.__class__.__name__}. "
                "Either initialize MCPApp first or pass context explicitly."
            ) from e

    @contextmanager
    def use_context(self, context: "Context"):
        """Temporarily use a different context."""
        old_context = self._context
        self._context = context
        try:
            yield
        finally:
            self._context = old_context
