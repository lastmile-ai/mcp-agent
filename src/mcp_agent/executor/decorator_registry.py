"""
Keep track of all workflow decorator overloads indexed by executor backend.
Different executors may have different ways of configuring workflows.
"""

import threading
from typing import Callable, Dict, Type, TypeVar

R = TypeVar("R")
T = TypeVar("T")
S = TypeVar("S")


class DecoratorRegistry:
    """Centralized decorator management with validation and metadata.

    This is implemented as a thread-safe singleton to ensure all threads
    (including Temporal worker threads) see the same registered decorators.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DecoratorRegistry, cls).__new__(cls)
                    cls._instance._workflow_defn_decorators = {}
                    cls._instance._workflow_run_decorators = {}
                    cls._instance._workflow_task_decorators = {}
                    cls._instance._workflow_signal_decorators = {}
                    cls._instance._registry_lock = threading.RLock()
                    cls._instance._initialized = True
        return cls._instance

    def __init__(self):
        # Only initialize once due to singleton pattern
        if not hasattr(self, "_initialized"):
            self._workflow_defn_decorators: Dict[str, Callable[[Type], Type]] = {}
            self._workflow_run_decorators: Dict[
                str, Callable[[Callable[..., R]], Callable[..., R]]
            ] = {}
            self._workflow_task_decorators: Dict[
                str, Callable[[Callable[..., T]], Callable[..., T]]
            ] = {}
            self._workflow_signal_decorators: Dict[
                str, Callable[[Callable[..., S]], Callable[..., S]]
            ] = {}
            self._registry_lock = threading.RLock()
            self._initialized = True

    def register_workflow_defn_decorator(
        self,
        executor_name: str,
        decorator: Callable[[Type], Type],
    ):
        """
        Registers a workflow definition decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :param decorator: The decorator to register.
        """
        with self._registry_lock:
            if executor_name in self._workflow_defn_decorators:
                print(
                    f"Workflow definition decorator already registered for '{executor_name}'. Overwriting."
                )
            self._workflow_defn_decorators[executor_name] = decorator

    def get_workflow_defn_decorator(self, executor_name: str) -> Callable[[Type], Type]:
        """
        Retrieves a workflow definition decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :return: The decorator function.
        """
        with self._registry_lock:
            return self._workflow_defn_decorators.get(executor_name)

    def register_workflow_run_decorator(
        self,
        executor_name: str,
        decorator: Callable[[Callable[..., R]], Callable[..., R]],
    ):
        """
        Registers a workflow run decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :param decorator: The decorator to register.
        """
        with self._registry_lock:
            if executor_name in self._workflow_run_decorators:
                print(
                    f"Workflow run decorator already registered for '{executor_name}'. Overwriting."
                )
            self._workflow_run_decorators[executor_name] = decorator

    def get_workflow_run_decorator(
        self, executor_name: str
    ) -> Callable[[Callable[..., R]], Callable[..., R]]:
        """
        Retrieves a workflow run decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :return: The decorator function.
        """
        with self._registry_lock:
            return self._workflow_run_decorators.get(executor_name)

    def register_workflow_task_decorator(
        self,
        executor_name: str,
        decorator: Callable[[Callable[..., T]], Callable[..., T]],
    ):
        """
        Registers a workflow task decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :param decorator: The decorator to register.
        """
        with self._registry_lock:
            if executor_name in self._workflow_task_decorators:
                print(
                    f"Workflow task decorator already registered for '{executor_name}'. Overwriting."
                )
            self._workflow_task_decorators[executor_name] = decorator

    def get_workflow_task_decorator(
        self, executor_name: str
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        Retrieves a workflow task decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :return: The decorator function.
        """
        with self._registry_lock:
            return self._workflow_task_decorators.get(executor_name)

    def register_workflow_signal_decorator(
        self,
        executor_name: str,
        decorator: Callable[[Callable[..., S]], Callable[..., S]],
    ):
        """
        Registers a workflow signal decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :param decorator: The decorator to register.
        """
        with self._registry_lock:
            if executor_name in self._workflow_signal_decorators:
                print(
                    f"Workflow signal decorator already registered for '{executor_name}'. Overwriting."
                )
            self._workflow_signal_decorators[executor_name] = decorator

    def get_workflow_signal_decorator(
        self, executor_name: str
    ) -> Callable[[Callable[..., S]], Callable[..., S]]:
        """
        Retrieves a workflow signal decorator for a given executor.

        :param executor_name: Unique name of the executor.
        :return: The decorator function.
        """
        with self._registry_lock:
            return self._workflow_signal_decorators.get(executor_name)


# Global singleton instance getter
def get_global_decorator_registry() -> DecoratorRegistry:
    """Get the global singleton DecoratorRegistry instance."""
    return DecoratorRegistry()


def default_workflow_defn(cls: Type, *args, **kwargs) -> Type:
    """Default no-op workflow definition decorator."""
    return cls


def default_workflow_run(fn: Callable[..., R]) -> Callable[..., R]:
    """Default no-op workflow run decorator."""

    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def default_workflow_task(fn: Callable[..., T]) -> Callable[..., T]:
    """Default no-op workflow task decorator."""

    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def default_workflow_signal(fn: Callable[..., R]) -> Callable[..., R]:
    """Default no-op workflow signal decorator."""

    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def register_asyncio_decorators(decorator_registry: DecoratorRegistry):
    """Registers default asyncio decorators."""
    executor_name = "asyncio"
    decorator_registry.register_workflow_defn_decorator(
        executor_name, default_workflow_defn
    )
    decorator_registry.register_workflow_run_decorator(
        executor_name, default_workflow_run
    )
    decorator_registry.register_workflow_signal_decorator(
        executor_name, default_workflow_signal
    )


def register_temporal_decorators(decorator_registry: DecoratorRegistry):
    """Registers Temporal decorators if Temporal SDK is available."""
    try:
        import temporalio.workflow as temporal_workflow
        import temporalio.activity as temporal_activity

        TEMPORAL_AVAILABLE = True
    except ImportError:
        TEMPORAL_AVAILABLE = False

    if not TEMPORAL_AVAILABLE:
        return

    executor_name = "temporal"
    decorator_registry.register_workflow_defn_decorator(
        executor_name, temporal_workflow.defn
    )
    decorator_registry.register_workflow_run_decorator(
        executor_name, temporal_workflow.run
    )
    decorator_registry.register_workflow_task_decorator(
        executor_name, temporal_activity.defn
    )
    decorator_registry.register_workflow_signal_decorator(
        executor_name, temporal_workflow.signal
    )
