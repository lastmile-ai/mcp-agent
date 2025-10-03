"""
Keep track of all activities/tasks that the executor needs to run.
This is used by the workflow engine to dynamically orchestrate a workflow graph.
The user just writes standard functions annotated with @workflow_task, but behind the scenes a workflow graph is built.
"""

from typing import Any, Callable, Dict, List


class ActivityRegistry:
    """Centralized task/activity management with validation and metadata."""

    def __init__(self):
        self._activities: Dict[str, Callable] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def register(
        self, name: str, func: Callable, metadata: Dict[str, Any] | None = None
    ):
        if name in self._activities:
            raise ValueError(f"Activity '{name}' is already registered.")
        self._activities[name] = func
        self._metadata[name] = metadata or {}

    def get_activity(self, name: str) -> Callable:
        if name not in self._activities:
            raise KeyError(f"Activity '{name}' not found.")
        return self._activities[name]

    def get_metadata(self, name: str) -> Dict[str, Any]:
        return self._metadata.get(name, {})

    def list_activities(self) -> List[str]:
        return list(self._activities.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an activity is already registered with the given name."""
        return name in self._activities
