"""Shared error helpers for workflow/task execution."""

from __future__ import annotations

try:  # Temporal optional dependency
    from temporalio.exceptions import ApplicationError as TemporalApplicationError

    _TEMPORAL_AVAILABLE = True
except Exception:  # pragma: no cover
    _TEMPORAL_AVAILABLE = False

    class TemporalApplicationError(RuntimeError):
        """Fallback ApplicationError used when Temporal SDK is not installed."""

        def __init__(
            self,
            message: str,
            *,
            type: str | None = None,
            non_retryable: bool = False,
            details: object | None = None,
        ):
            super().__init__(message)
            self.type = type
            self.non_retryable = non_retryable
            self.details = details


class WorkflowApplicationError(TemporalApplicationError):
    """ApplicationError wrapper compatible with and without Temporal installed."""

    def __init__(
        self,
        message: str,
        *,
        type: str | None = None,
        non_retryable: bool = False,
        details: object | None = None,
        **kwargs: object,
    ):
        normalized_details = details
        if isinstance(normalized_details, tuple):
            normalized_details = list(normalized_details)

        self._workflow_details_fallback = normalized_details

        if _TEMPORAL_AVAILABLE:
            detail_args: tuple = ()
            if normalized_details is not None:
                if isinstance(normalized_details, list):
                    detail_args = tuple(normalized_details)
                else:
                    detail_args = (normalized_details,)

            super().__init__(
                message,
                *detail_args,
                type=type,
                non_retryable=non_retryable,
                **kwargs,
            )

            if not hasattr(self, "non_retryable"):
                setattr(self, "non_retryable", non_retryable)
        else:
            super().__init__(
                message,
                type=type,
                non_retryable=non_retryable,
                details=normalized_details,
            )

    @property
    def workflow_details(self):
        details = getattr(self, "details", None)
        if details:
            if isinstance(details, tuple):
                return list(details)
            return details
        return self._workflow_details_fallback


def to_application_error(
    error: BaseException,
    *,
    message: str | None = None,
    type: str | None = None,
    non_retryable: bool | None = None,
    details: object | None = None,
) -> WorkflowApplicationError:
    """Wrap an existing exception as a WorkflowApplicationError."""

    msg = message or str(error)
    err_type = type or getattr(error, "type", None) or error.__class__.__name__
    nr = non_retryable
    if nr is None:
        nr = bool(getattr(error, "non_retryable", False))
    det = details
    if det is None:
        det = getattr(error, "details", None)
    if isinstance(det, tuple):
        det = list(det)
    return WorkflowApplicationError(msg, type=err_type, non_retryable=nr, details=det)


__all__ = ["WorkflowApplicationError", "to_application_error"]
