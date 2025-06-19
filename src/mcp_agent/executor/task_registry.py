"""
Keep track of all activities/tasks that the executor needs to run.
This is used by the workflow engine to dynamically orchestrate a workflow graph.
The user just writes standard functions annotated with @workflow_task, but behind the scenes a workflow graph is built.
"""

import threading
from typing import Any, Callable, Dict, List


class ActivityRegistry:
    """Centralized task/activity management with validation and metadata.

    This is implemented as a thread-safe singleton to ensure all threads
    (including Temporal worker threads) see the same registered activities.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ActivityRegistry, cls).__new__(cls)
                    cls._instance._activities = {}
                    cls._instance._metadata = {}
                    cls._instance._registry_lock = threading.RLock()
                    cls._instance._initialized = True
        return cls._instance

    def __init__(self):
        # Only initialize once due to singleton pattern
        if not hasattr(self, "_initialized"):
            self._activities: Dict[str, Callable] = {}
            self._metadata: Dict[str, Dict[str, Any]] = {}
            self._registry_lock = threading.RLock()
            self._initialized = True

    def register(
        self, name: str, func: Callable, metadata: Dict[str, Any] | None = None
    ):
        with self._registry_lock:
            if name in self._activities:
                raise ValueError(f"Activity '{name}' is already registered.")
            self._activities[name] = func
            self._metadata[name] = metadata or {}

    def get_activity(self, name: str) -> Callable:
        with self._registry_lock:
            if name not in self._activities:
                raise KeyError(f"Activity '{name}' not found.")
            return self._activities[name]

    def get_metadata(self, name: str) -> Dict[str, Any]:
        with self._registry_lock:
            return self._metadata.get(name, {})

    def list_activities(self) -> List[str]:
        with self._registry_lock:
            return list(self._activities.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an activity is already registered with the given name."""
        with self._registry_lock:
            return name in self._activities


# Global singleton instance getter
def get_global_activity_registry() -> ActivityRegistry:
    """Get the global singleton ActivityRegistry instance."""
    return ActivityRegistry()
