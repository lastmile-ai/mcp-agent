import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_agent.executor.temporal.workflow_signal import TemporalSignalHandler
from mcp_agent.executor.workflow_signal import Signal, SignalMailbox


@pytest.fixture
def mailbox():
    return SignalMailbox()


def test_push_and_version(mailbox):
    mailbox.push("signal1", "value1")
    assert mailbox.version("signal1") == 1
    assert mailbox.value("signal1") == "value1"
    mailbox.push("signal1", "value2")
    assert mailbox.version("signal1") == 2
    assert mailbox.value("signal1") == "value2"


def test_value_not_exists(mailbox):
    with pytest.raises(ValueError):
        mailbox.value("nonexistent")


def test_version_not_exists(mailbox):
    assert mailbox.version("nonexistent") == 0


@pytest.fixture
def mock_executor():
    return AsyncMock()


@pytest.fixture
def handler(mock_executor):
    return TemporalSignalHandler(executor=mock_executor)


@pytest.fixture
def mock_workflow():
    workflow = MagicMock(name="test_workflow")
    workflow._signal_mailbox = SignalMailbox()
    return workflow


def test_attach_to_workflow(handler, mock_workflow):
    handler.attach_to_workflow(mock_workflow)
    # MagicMock does not set real attributes, so cast to bool
    assert bool(mock_workflow._signal_handler_attached) is True
    # Idempotence
    handler.attach_to_workflow(mock_workflow)


@pytest.mark.asyncio
@patch("temporalio.workflow.in_workflow", return_value=True)
async def test_wait_for_signal(_mock_in_wf, handler, mock_workflow):
    handler.attach_to_workflow(mock_workflow)
    # Patch the handler's ContextVar to point to the mock_workflow's mailbox
    handler._mailbox_ref.set(mock_workflow._signal_mailbox)
    signal = Signal(name="test_signal", payload="test_value")
    mock_workflow._signal_mailbox.push(signal.name, signal.payload)
    with patch("temporalio.workflow.wait_condition", AsyncMock()):
        result = await handler.wait_for_signal(signal)
        assert result == "test_value"


@pytest.mark.asyncio
@patch("temporalio.workflow.in_workflow", return_value=True)
async def test_wait_for_signal_timeout(_mock_in_wf, handler, mock_workflow):
    handler.attach_to_workflow(mock_workflow)
    # Patch the handler's ContextVar to point to the mock_workflow's mailbox
    handler._mailbox_ref.set(mock_workflow._signal_mailbox)
    signal = Signal(name="test_signal", payload="test_value")
    with patch(
        "temporalio.workflow.wait_condition",
        AsyncMock(side_effect=asyncio.TimeoutError),
    ):
        with pytest.raises(TimeoutError):
            await handler.wait_for_signal(signal, timeout_seconds=1)


@pytest.mark.asyncio
@patch("temporalio.workflow.in_workflow", return_value=False)
@patch(
    "temporalio.workflow.get_external_workflow_handle",
    side_effect=__import__("temporalio.workflow").workflow._NotInWorkflowEventLoopError(
        "Not in workflow event loop"
    ),
)
async def test_signal_outside_workflow(
    mock_get_external, _mock_in_wf, handler, mock_executor
):
    signal = Signal(
        name="test_signal",
        payload="test_value",
        workflow_id="workflow-id",
        run_id="run-id",
    )

    # Use MagicMock with async signal method
    mock_handle = MagicMock()
    mock_handle.signal = AsyncMock()
    mock_executor.client.get_workflow_handle = MagicMock(return_value=mock_handle)
    await handler.signal(signal)
    mock_executor.ensure_client.assert_awaited_once()
    mock_executor.client.get_workflow_handle.assert_called_once_with(
        workflow_id="workflow-id", run_id="run-id"
    )
    mock_handle.signal.assert_awaited_once_with("test_signal", "test_value")
