import pytest

from mcp_agent.executor.errors import WorkflowApplicationError, to_application_error


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
