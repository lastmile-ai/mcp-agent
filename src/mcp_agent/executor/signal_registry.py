import threading
from typing import Any, Callable, Dict, List


class SignalRegistry:
    """Centralized signals management.

    This is implemented as a thread-safe singleton to ensure all threads
    (including Temporal worker threads) see the same registered signals.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SignalRegistry, cls).__new__(cls)
                    cls._instance._signals = {}
                    cls._instance._state = {}
                    cls._instance._registry_lock = threading.RLock()
                    cls._instance._initialized = True
        return cls._instance

    def __init__(self):
        # Only initialize once due to singleton pattern
        if not hasattr(self, "_initialized"):
            self._signals: Dict[str, Callable] = {}
            self._state: Dict[str, Dict[str, Any]] = {}
            self._registry_lock = threading.RLock()
            self._initialized = True

    def register(self, name: str, func: Callable, state: Dict[str, Any] | None = None):
        with self._registry_lock:
            if name in self._signals:
                raise ValueError(f"Signal handler '{name}' is already registered.")
            self._signals[name] = func
            self._state[name] = state or {}

    def get_signal(self, name: str) -> Callable:
        with self._registry_lock:
            if name not in self._signals:
                raise KeyError(f"Signal handler '{name}' not found.")
            return self._signals[name]

    def get_state(self, name: str) -> Dict[str, Any]:
        with self._registry_lock:
            return self._state.get(name, {})

    def list_signals(self) -> List[str]:
        with self._registry_lock:
            return list(self._signals.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an Signal handler is already registered with the given name."""
        with self._registry_lock:
            return name in self._signals


# Global singleton instance getter
def get_global_signal_registry() -> SignalRegistry:
    """Get the global singleton SignalRegistry instance."""
    return SignalRegistry()
