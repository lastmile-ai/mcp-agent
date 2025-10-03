from typing import Any, Callable, Dict, List


class SignalRegistry:
    """Centralized signals management"""

    def __init__(self):
        self._signals: Dict[str, Callable] = {}
        self._state: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, func: Callable, state: Dict[str, Any] | None = None):
        if name in self._signals:
            raise ValueError(f"Signal handler '{name}' is already registered.")
        self._signals[name] = func
        self._state[name] = state or {}

    def get_signal(self, name: str) -> Callable:
        if name not in self._signals:
            raise KeyError(f"Signal handler '{name}' not found.")
        return self._signals[name]

    def get_state(self, name: str) -> Dict[str, Any]:
        return self._state.get(name, {})

    def list_signals(self) -> List[str]:
        return list(self._signals.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an Signal handler is already registered with the given name."""
        return name in self._signals
