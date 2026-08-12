from types import SimpleNamespace

import pytest

from mcp_agent.executor.errors import (
    WorkflowApplicationError,
    reraise_with_workflow_failure,
    to_application_error,
)
from mcp_agent.executor.workflow import WorkflowState


def test_workflow_application_error_attributes():
    err = WorkflowApplicationError("message", type="CustomType", non_retryable=True)
    assert isinstance(err, Exception)
    assert getattr(err, "type", None) == "CustomType"
    assert getattr(err, "non_retryable", None) is True


@pytest.mark.parametrize("extra_kw", [{"details": ["foo"]}, {}])
def test_workflow_application_error_accepts_additional_kwargs(extra_kw):
    # Temporal's ApplicationError accepts details; ensure our wrapper tolerates it
    err = WorkflowApplicationError("msg", type="T", non_retryable=False, **extra_kw)
    msg_attr = getattr(err, "message", None)
    if msg_attr is None and err.args:
        msg_attr = err.args[0]
    assert "msg" in str(err)
    if msg_attr is not None:
        assert "msg" in str(msg_attr)
    assert getattr(err, "type", None) == "T"
    if "details" in extra_kw:
        details = getattr(err, "workflow_details", None)
        assert details == extra_kw["details"]


def test_to_application_error_from_exception():
    class CustomError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.type = "Custom"
            self.non_retryable = True
            self.details = ["detail"]

    original = CustomError("boom")
    converted = to_application_error(original)
    assert isinstance(converted, WorkflowApplicationError)
    assert converted.type == "Custom"
    assert converted.non_retryable is True
    assert converted.workflow_details == ["detail"]


def test_reraise_with_workflow_failure_converts_plain_exception():
    """Plain exceptions become non-retryable ApplicationErrors (issue #503)."""
    state = WorkflowState()
    statuses: list[str] = []

    instance = SimpleNamespace(
        state=state,
        update_status=lambda status: statuses.append(status),
    )

    with pytest.raises(WorkflowApplicationError) as excinfo:
        reraise_with_workflow_failure(
            RuntimeError("TEST"), instance=instance, for_temporal=True
        )

    err = excinfo.value
    assert err.non_retryable is True
    assert err.type == "RuntimeError"
    assert "TEST" in str(err)
    assert statuses == ["error"]
    assert state.error is not None
    assert state.error["type"] == "RuntimeError"
    assert state.error["message"] == "TEST"


def test_reraise_with_workflow_failure_preserves_plain_exception_for_asyncio():
    """Non-Temporal engines must preserve the original exception type."""
    state = WorkflowState()
    statuses: list[str] = []

    instance = SimpleNamespace(
        state=state,
        update_status=lambda status: statuses.append(status),
    )

    with pytest.raises(RuntimeError) as excinfo:
        reraise_with_workflow_failure(
            RuntimeError("TEST"), instance=instance, for_temporal=False
        )

    assert str(excinfo.value) == "TEST"
    assert statuses == ["error"]
    assert state.error is not None
    assert state.error["type"] == "RuntimeError"
    assert state.error["message"] == "TEST"


def test_reraise_with_workflow_failure_preserves_application_error():
    original = WorkflowApplicationError(
        "already app error", type="SignalTimeout", non_retryable=True
    )
    with pytest.raises(WorkflowApplicationError) as excinfo:
        reraise_with_workflow_failure(original, for_temporal=True)

    assert excinfo.value is original


def test_reraise_with_workflow_failure_preserves_temporal_failure_error():
    pytest.importorskip("temporalio")
    from temporalio.exceptions import ApplicationError

    original = ApplicationError("temporal app err", type="Custom", non_retryable=False)
    with pytest.raises(ApplicationError) as excinfo:
        reraise_with_workflow_failure(original, for_temporal=True)

    assert excinfo.value is original
    assert excinfo.value.non_retryable is False
