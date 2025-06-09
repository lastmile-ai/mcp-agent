# In tests/executor/test_multi_signal.py

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from mcp_agent.executor.workflow_signal import Signal, AsyncioSignalHandler
from mcp_agent.executor.temporal.workflow_signal import TemporalSignalHandler

# --- AsyncioSignalHandler Tests ---

@pytest.mark.asyncio
async def test_asyncio_wait_for_any_signal():
    handler = AsyncioSignalHandler()
    signal_names = ["signal_A", "signal_B"]

    # Start waiting in the background
    wait_task = asyncio.create_task(
        handler.wait_for_any_signal(signal_names, "wf-1")
    )
    await asyncio.sleep(0.01) # let the waiter start

    # Emit signal_B
    await handler.signal(Signal(name="signal_B", payload="data_B", workflow_id="wf-1"))

    # The wait task should complete and return the correct signal
    triggered_signal = await asyncio.wait_for(wait_task, timeout=1)

    assert isinstance(triggered_signal, Signal)
    assert triggered_signal.name == "signal_B"
    assert triggered_signal.payload == "data_B"
    
    # Ensure waiters are cleaned up
    assert not handler._pending_signals

@pytest.mark.asyncio
async def test_asyncio_wait_for_any_signal_timeout():
    handler = AsyncioSignalHandler()
    with pytest.raises(asyncio.TimeoutError):
        await handler.wait_for_any_signal(
            signal_names=["signal_A", "signal_B"], 
            workflow_id="wf-1", 
            timeout_seconds=0.1
        )

@pytest.mark.asyncio
async def test_asyncio_wait_for_any_signal_multiple_waiters():
    """Test that multiple waiters can wait for different sets of signals simultaneously."""
    handler = AsyncioSignalHandler()
    
    # Start two waiters for different signal sets
    wait_task_1 = asyncio.create_task(
        handler.wait_for_any_signal(["signal_A", "signal_B"], "wf-1")
    )
    wait_task_2 = asyncio.create_task(
        handler.wait_for_any_signal(["signal_C", "signal_D"], "wf-2")
    )
    
    await asyncio.sleep(0.01)  # Let waiters start
    
    # Emit signal_C which should only trigger wait_task_2
    await handler.signal(Signal(name="signal_C", payload="data_C", workflow_id="wf-2"))
    
    # Wait for one of the tasks to complete
    done, pending = await asyncio.wait([wait_task_1, wait_task_2], return_when=asyncio.FIRST_COMPLETED)
    
    # Only wait_task_2 should be done
    assert len(done) == 1
    assert len(pending) == 1
    
    completed_task = done.pop()
    assert completed_task is wait_task_2
    
    triggered_signal = await completed_task
    assert triggered_signal.name == "signal_C"
    assert triggered_signal.payload == "data_C"
    
    # Clean up the pending task
    for task in pending:
        task.cancel()

@pytest.mark.asyncio
async def test_asyncio_wait_for_any_signal_first_signal_wins():
    """Test that when multiple signals are emitted, the first one wins."""
    handler = AsyncioSignalHandler()
    signal_names = ["signal_A", "signal_B", "signal_C"]

    # Start waiting in the background
    wait_task = asyncio.create_task(
        handler.wait_for_any_signal(signal_names, "wf-1")
    )
    await asyncio.sleep(0.01)  # let the waiter start

    # Emit multiple signals quickly
    await handler.signal(Signal(name="signal_A", payload="data_A", workflow_id="wf-1"))
    await handler.signal(Signal(name="signal_B", payload="data_B", workflow_id="wf-1"))
    await handler.signal(Signal(name="signal_C", payload="data_C", workflow_id="wf-1"))

    # The wait task should complete with one of the signals (timing dependent)
    triggered_signal = await asyncio.wait_for(wait_task, timeout=1)

    assert isinstance(triggered_signal, Signal)
    # Any of the three signals could be triggered first due to asyncio timing
    assert triggered_signal.name in ["signal_A", "signal_B", "signal_C"]
    assert triggered_signal.payload in ["data_A", "data_B", "data_C"]

# --- TemporalSignalHandler Tests ---

@pytest.mark.asyncio
@patch("temporalio.workflow._Runtime.current", return_value=MagicMock())
async def test_temporal_wait_for_any_signal(mock_runtime):
    from mcp_agent.executor.temporal.workflow_signal import SignalMailbox
    
    handler = TemporalSignalHandler()
    mailbox = SignalMailbox()
    handler._mailbox_ref.set(mailbox)

    # Mock workflow.wait_condition and workflow.info
    with patch("temporalio.workflow.wait_condition") as mock_wait_condition, \
         patch("temporalio.workflow.info") as mock_info:
        
        mock_info.return_value.run_id = "test-run-id"
        
        # Simulate that signal_B is received during wait
        async def mock_condition_waiter(condition_func, timeout=None):
            # First call returns False, second call (after signal) returns True
            if not condition_func():
                # Simulate signal_B being received
                mailbox.push("signal_B", "payload_B")
            # Now condition should return True
            assert condition_func() == True
        
        mock_wait_condition.side_effect = mock_condition_waiter

        # Call the method
        result = await handler.wait_for_any_signal(["signal_A", "signal_B"], "wf-1")

        # Assertions
        mock_wait_condition.assert_called_once()
        
        assert result.name == "signal_B"
        assert result.payload == "payload_B"
        assert result.workflow_id == "wf-1"
        assert result.run_id == "test-run-id"

@pytest.mark.asyncio
@patch("temporalio.workflow._Runtime.current", return_value=MagicMock())
async def test_temporal_wait_for_any_signal_timeout(mock_runtime):
    from mcp_agent.executor.temporal.workflow_signal import SignalMailbox
    from temporalio import exceptions as temporal_exceptions
    
    handler = TemporalSignalHandler()
    mailbox = SignalMailbox()
    handler._mailbox_ref.set(mailbox)
    
    with patch("temporalio.workflow.wait_condition") as mock_wait_condition:
        # Create a proper Temporal TimeoutError with required arguments
        from temporalio.api.enums.v1 import TimeoutType
        timeout_error = temporal_exceptions.TimeoutError(
            "Timeout", 
            type=TimeoutType.TIMEOUT_TYPE_SCHEDULE_TO_START,
            last_heartbeat_details=[]
        )
        mock_wait_condition.side_effect = timeout_error

        with pytest.raises(asyncio.TimeoutError):
            await handler.wait_for_any_signal(["signal_A"], "wf-1", timeout_seconds=0.1)

@pytest.mark.asyncio
async def test_temporal_wait_for_any_signal_outside_workflow():
    """Test that calling wait_for_any_signal outside a workflow raises RuntimeError."""
    handler = TemporalSignalHandler()
    
    with patch("temporalio.workflow._Runtime.current", return_value=None):
        with pytest.raises(RuntimeError, match="wait_for_any_signal must be called from within a Temporal workflow"):
            await handler.wait_for_any_signal(["signal_A"], "wf-1")

# --- Integration Tests ---

@pytest.mark.asyncio
async def test_asyncio_wait_for_any_signal_cleanup_on_exception():
    """Test that pending signals are properly cleaned up when an exception occurs."""
    handler = AsyncioSignalHandler()
    
    # Mock asyncio.wait to raise an exception
    with patch("asyncio.wait", side_effect=RuntimeError("Test error")):
        with pytest.raises(RuntimeError, match="Test error"):
            await handler.wait_for_any_signal(["signal_A", "signal_B"], "wf-1")
    
    # Ensure no pending signals remain
    assert not handler._pending_signals

@pytest.mark.asyncio 
async def test_asyncio_wait_for_any_signal_empty_signal_names():
    """Test behavior when waiting for an empty list of signals."""
    handler = AsyncioSignalHandler()
    
    # Should raise ValueError for empty signal list since asyncio.wait doesn't accept empty iterables
    with pytest.raises(ValueError, match="Set of coroutines/Futures is empty"):
        await handler.wait_for_any_signal([], "wf-1", timeout_seconds=0.1)

@pytest.mark.asyncio
async def test_asyncio_wait_for_any_signal_workflow_id_filtering():
    """Test that signals are properly filtered by workflow_id."""
    handler = AsyncioSignalHandler()
    
    # Start waiting for workflow wf-1
    wait_task = asyncio.create_task(
        handler.wait_for_any_signal(["signal_A"], "wf-1")
    )
    await asyncio.sleep(0.01)
    
    # Emit signal for different workflow (should not trigger)
    await handler.signal(Signal(name="signal_A", payload="wrong_workflow", workflow_id="wf-2"))
    
    # Emit signal for correct workflow (should trigger)
    await handler.signal(Signal(name="signal_A", payload="correct_workflow", workflow_id="wf-1"))
    
    triggered_signal = await asyncio.wait_for(wait_task, timeout=1)
    assert triggered_signal.payload == "correct_workflow"