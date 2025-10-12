from __future__ import annotations

from typing import Iterable, List, Mapping


class BudgetError(Exception):
    """Raised when assembling context exceeds a configured budget."""

    def __init__(
        self,
        overflow: Iterable[Mapping[str, object]] | None = None,
        message: str = "Resource budget exceeded during assembly",
    ) -> None:
        normalized: List[Mapping[str, object]] = []
        for item in overflow or []:
            if hasattr(item, "model_dump"):
                normalized.append(item.model_dump())  # type: ignore[arg-type]
            else:
                try:
                    normalized.append(dict(item))  # type: ignore[arg-type]
                except Exception:
                    normalized.append({"value": repr(item)})
        detail = f" ({len(normalized)} overflow items)" if normalized else ""
        super().__init__(f"{message}{detail}")
        self.overflow = list(normalized)
