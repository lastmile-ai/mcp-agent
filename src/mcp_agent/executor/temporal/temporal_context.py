from typing import Optional

EXECUTION_ID_KEY = "__execution_id"

_EXECUTION_ID: str | None = None


def set_execution_id(execution_id: Optional[str]) -> None:
    global _EXECUTION_ID
    _EXECUTION_ID = execution_id


def get_execution_id() -> Optional[str]:
    return _EXECUTION_ID
