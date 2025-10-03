"""
Static decorator registry for @workflow_task.
Wherever possible it is preferred to use @app.workflow_task in MCPApp
"""

from typing import Any, Dict, List, Callable, TypeVar
from datetime import timedelta
import asyncio

from mcp_agent.utils.common import unwrap

R = TypeVar("R")


# Global registry to store statically defined workflow tasks
class GlobalWorkflowTaskRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalWorkflowTaskRegistry, cls).__new__(cls)
            cls._instance._tasks = []
        return cls._instance

    def register_task(self, func: Callable, metadata: Dict[str, Any]):
        self._tasks.append((func, metadata))

    def get_all_tasks(self) -> List[tuple]:
        return self._tasks

    def clear(self):
        self._tasks = []


# Static decorator for workflow tasks
def workflow_task(
    _fn: Callable[..., R] | None = None,
    *,
    name: str = None,
    schedule_to_close_timeout: timedelta = None,
    retry_policy: Dict[str, Any] = None,
    **meta_kwargs,
) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """
    Static decorator to mark a function as a workflow task without requiring direct app access.
    These tasks will be registered with the MCPApp during app initialization.

    Args:
        name: Optional custom name for the activity
        schedule_to_close_timeout: Maximum time the task can take to complete
        retry_policy: Retry policy configuration
        **meta_kwargs: Additional metadata passed to the activity registration

    Returns:
        Decorated function that preserves async and typing information
    """

    def decorator(target: Callable[..., R]) -> Callable[..., R]:
        func = unwrap(target)  # Get the underlying function

        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"{func.__qualname__} must be async")

        activity_name = name or f"{func.__module__}.{func.__qualname__}"
        metadata = {
            "activity_name": activity_name,
            "schedule_to_close_timeout": schedule_to_close_timeout
            or timedelta(minutes=10),
            "retry_policy": retry_policy or {},
            **meta_kwargs,
        }

        # Store the function information in the static registry
        # We store the raw function and let the app apply the appropriate decorators later
        registry = GlobalWorkflowTaskRegistry()
        registry.register_task(target, metadata)

        # Mark the function as a workflow task
        func.is_workflow_task = True
        func.execution_metadata = metadata

        # Return the original function - the actual decoration will happen when registered with the app
        return target

    # Called **with** parentheses → _fn is None → return decorator
    if _fn is None:
        return decorator

    # Called **without** parentheses → _fn is the target → decorate now
    return decorator(_fn)
