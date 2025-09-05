from typing import Optional
from contextvars import ContextVar

EXECUTION_ID_KEY = "__execution_id"

_EXECUTION_ID: ContextVar[Optional[str]] = ContextVar("execution_id", default=None)


def set_execution_id(execution_id: Optional[str]) -> None:
    _EXECUTION_ID.set(execution_id)


def get_execution_id() -> Optional[str]:
    return _EXECUTION_ID.get()
