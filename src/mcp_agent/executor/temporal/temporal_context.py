from typing import Optional

EXECUTION_ID_KEY = "__execution_id"

_execution_id: Optional[str] = None


def set_execution_id(execution_id: str) -> None:
    global _execution_id
    _execution_id = execution_id


def get_execution_id() -> Optional[str]:
    return _execution_id
