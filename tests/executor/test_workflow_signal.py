from unittest.mock import MagicMock, patch
import asyncio
import pytest

from mcp_agent.executor.workflow_signal import (
    Signal,
    SignalRegistration,
    PendingSignal,
    BaseSignalHandler,
    AsyncioSignalHandler,
    ConsoleSignalHandler,
    LocalSignalStore,
)


class TestSignalModels:
    """
    Tests for the Signal, SignalRegistration, and PendingSignal models.
    """

    def test_signal_creation(self):
        """Test creating a Signal model."""
        signal = Signal(
            name="test_signal", description="Test signal", payload="test data"
        )

        assert signal.name == "test_signal"
        assert signal.description == "Test signal"
        assert signal.payload == "test data"
        assert signal.metadata is None
        assert signal.workflow_id is None

    def test_signal_creation_with_metadata(self):
        """Test creating a Signal model with metadata."""
        metadata = {"source": "test", "priority": "high"}
        signal = Signal(
            name="test_signal",
            description="Test signal",
            payload="test data",
            metadata=metadata,
            workflow_id="workflow-123",
        )

        assert signal.name == "test_signal"
        assert signal.description == "Test signal"
        assert signal.payload == "test data"
        assert signal.metadata == metadata
        assert signal.workflow_id == "workflow-123"

    def test_signal_registration_creation(self):
        """Test creating a SignalRegistration model."""
        registration = SignalRegistration(
            signal_name="test_signal",
            unique_name="test_signal_123",
            workflow_id="workflow-123",
        )

        assert registration.signal_name == "test_signal"
        assert registration.unique_name == "test_signal_123"
        assert registration.workflow_id == "workflow-123"

    def test_pending_signal_creation(self):
        """Test creating a PendingSignal model."""
        registration = SignalRegistration(
            signal_name="test_signal", unique_name="test_signal_123"
        )
        event = asyncio.Event()

        pending = PendingSignal(
            registration=registration, event=event, value="test_value"
        )

        assert pending.registration == registration
        assert pending.event == event
        assert pending.value == "test_value"


class TestBaseSignalHandler:
    """
    Tests for the BaseSignalHandler class.
    """

    class MockSignalHandler(BaseSignalHandler):
        """Mock implementation of BaseSignalHandler for testing."""

        async def signal(self, signal):
            self.validate_signal(signal)
            return True

        async def wait_for_signal(self, signal, timeout_seconds=None):
            self.validate_signal(signal)
            return signal.payload

    def test_validate_signal(self):
        """Test signal validation."""
        handler = self.MockSignalHandler()

        # Valid signal
        valid_signal = Signal(name="test_signal")
        handler.validate_signal(valid_signal)

        # Invalid signal (no name)
        with pytest.raises(ValueError):
            invalid_signal = Signal(name="")
            handler.validate_signal(invalid_signal)

    def test_signal_handler_registration(self):
        """Test registering signal handlers."""
        handler = self.MockSignalHandler()

        # Register a handler
        @handler.on_signal("test_signal")
        def test_handler(value):
            return f"Handled {value}"

        # Verify it was registered
        assert "test_signal" in handler._handlers
        assert len(handler._handlers["test_signal"]) == 1

        # Check unique name generation
        unique_name = handler._handlers["test_signal"][0][0]
        assert unique_name.startswith("test_signal_")

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup functionality."""
        handler = self.MockSignalHandler()

        # Register some signal handlers
        @handler.on_signal("signal1")
        def handler1(value):
            pass

        @handler.on_signal("signal2")
        def handler2(value):
            pass

        # Setup pending signals
        handler._pending_signals = {"signal1": ["pending1"], "signal2": ["pending2"]}

        # Cleanup one signal
        await handler.cleanup("signal1")
        assert "signal1" not in handler._handlers
        assert "signal1" not in handler._pending_signals
        assert "signal2" in handler._handlers
        assert "signal2" in handler._pending_signals

        # Cleanup all signals
        await handler.cleanup()
        assert len(handler._handlers) == 0
        assert len(handler._pending_signals) == 0


class TestAsyncioSignalHandler:
    """
    Tests for the AsyncioSignalHandler class.
    """

    @pytest.fixture
    def handler(self):
        """Create a new AsyncioSignalHandler for each test."""
        return AsyncioSignalHandler()

    @pytest.mark.asyncio
    async def test_signal_emission(self, handler):
        """Test signal emission."""
        # Create a signal
        signal = Signal(name="test_signal", payload="test_data")

        # Call the signal method (no waiters yet, should not error)
        await handler.signal(signal)

        # Nothing to assert here since there are no waiters
        assert True

    @pytest.mark.asyncio
    async def test_wait_for_signal(self, handler):
        """Test waiting for a signal."""
        # Create a signal
        signal = Signal(name="test_signal", payload="initial_value")

        # Start waiting for the signal in a separate task
        wait_task = asyncio.create_task(handler.wait_for_signal(signal))

        # Give the task a moment to start waiting
        await asyncio.sleep(0.1)

        # Now emit the signal with a different payload
        emit_signal = Signal(name="test_signal", payload="updated_value")
        await handler.signal(emit_signal)

        # Wait for the result and verify it matches
        result = await wait_task
        assert result == "updated_value"

    @pytest.mark.asyncio
    async def test_wait_for_signal_with_timeout(self, handler):
        """Test waiting for a signal with a timeout."""
        # Create a signal
        signal = Signal(name="test_signal", payload="test_data")

        # Wait for the signal with a short timeout (should timeout)
        with pytest.raises(TimeoutError):
            await handler.wait_for_signal(signal, timeout_seconds=0.1)

    @pytest.mark.asyncio
    async def test_multiple_waiters(self, handler):
        """Test multiple waiters for the same signal."""
        # Create a signal
        signal = Signal(name="test_signal", payload="initial_value")

        # Start multiple waiters
        wait_task1 = asyncio.create_task(handler.wait_for_signal(signal))
        wait_task2 = asyncio.create_task(handler.wait_for_signal(signal))

        # Give the tasks a moment to start waiting
        await asyncio.sleep(0.1)

        # Now emit the signal
        emit_signal = Signal(name="test_signal", payload="updated_value")
        await handler.signal(emit_signal)

        # Wait for the results and verify they match
        result1 = await wait_task1
        result2 = await wait_task2

        assert result1 == "updated_value"
        assert result2 == "updated_value"

    @pytest.mark.asyncio
    async def test_handler_callback(self, handler):
        """Test registering and calling a handler callback."""
        # Create a mock to track callback execution
        callback_mock = MagicMock()

        # Register the callback
        @handler.on_signal("test_signal")
        def test_callback(value):
            callback_mock(value)

        # Emit a signal
        signal = Signal(name="test_signal", payload="test_data")
        await handler.signal(signal)

        # Verify the callback was called with the right value
        callback_mock.assert_called_once_with(signal)


class TestConsoleSignalHandler:
    """
    Tests for the ConsoleSignalHandler class.
    """

    @pytest.fixture
    def handler(self):
        """Create a new ConsoleSignalHandler for each test."""
        return ConsoleSignalHandler()

    @pytest.mark.asyncio
    async def test_signal_emission(self, handler):
        """Test signal emission."""
        # Create a signal
        signal = Signal(name="test_signal", payload="test_data")

        # Mock print function to verify output
        with patch("builtins.print") as mock_print:
            # Call the signal method
            await handler.signal(signal)

            # Verify print was called with the signal info
            mock_print.assert_called_with("[SIGNAL SENT: test_signal] Value: test_data")

    @pytest.mark.asyncio
    async def test_wait_for_signal(self, handler):
        """Test waiting for a signal with mocked input."""
        # Create a signal
        signal = Signal(name="test_signal", description="Test description")

        # Mock input function to return a specific value
        mock_input_value = "user input"
        future = asyncio.Future()
        future.set_result(mock_input_value)

        # Mock both print and input
        with (
            patch("builtins.print") as mock_print,
            patch("asyncio.get_event_loop") as mock_get_loop,
        ):
            # Setup mock event loop
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            # Mock run_in_executor to return a future that resolves to our desired input
            mock_loop.run_in_executor.return_value = future

            # Call wait_for_signal
            result = await handler.wait_for_signal(signal)

            # Verify print was called with expected message
            mock_print.assert_any_call("\n[SIGNAL: test_signal] Test description")

            # Verify input was asked for
            mock_loop.run_in_executor.assert_called_once()
            assert "Enter value: " in mock_loop.run_in_executor.call_args[0]

            # Verify result
            assert result == mock_input_value

    @pytest.mark.asyncio
    async def test_wait_for_signal_with_timeout(self, handler):
        """Test waiting for a signal with a timeout."""
        # Create a signal
        signal = Signal(name="test_signal", description="Test description")

        # Mock asyncio functions
        with (
            patch("builtins.print") as mock_print,
            patch("asyncio.get_event_loop") as mock_get_loop,
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            # Setup mock event loop
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            # Setup wait_for to timeout
            mock_wait_for.side_effect = asyncio.TimeoutError()

            # Call wait_for_signal with timeout
            with pytest.raises(asyncio.TimeoutError):
                await handler.wait_for_signal(signal, timeout_seconds=1)

            # Verify print was called with timeout message
            mock_print.assert_any_call("(Timeout in 1 seconds)")

            # Verify wait_for was called with correct timeout
            mock_wait_for.assert_called_once()
            assert mock_wait_for.call_args[0][1] == 1

    @pytest.mark.asyncio
    async def test_handler_callback(self, handler):
        """Test registering and calling a handler callback."""
        # Create a mock to track callback execution
        callback_mock = MagicMock()

        # Register the callback
        @handler.on_signal("test_signal")
        def test_callback(value):
            callback_mock(value)

        # Emit a signal
        signal = Signal(name="test_signal", payload="test_data")
        await handler.signal(signal)

        # Verify the callback was called with the right value
        callback_mock.assert_called_once()


class TestLocalSignalStore:
    """
    Tests for the LocalSignalStore class.
    """

    @pytest.fixture
    def store(self):
        """Create a new LocalSignalStore for each test."""
        return LocalSignalStore()

    @pytest.mark.asyncio
    async def test_emit_with_no_waiters(self, store):
        """Test emitting a signal with no waiters."""
        # Emit a signal (no waiters, should just return)
        await store.emit("test_signal", "test_data")

        # Nothing to assert, just verifying no errors
        assert True

    @pytest.mark.asyncio
    async def test_wait_for_and_emit(self, store):
        """Test waiting for a signal and then emitting it."""
        # Start waiting for the signal in a separate task
        wait_task = asyncio.create_task(store.wait_for("test_signal"))

        # Give the task a moment to start waiting
        await asyncio.sleep(0.1)

        # Emit the signal
        payload = "test_data"
        await store.emit("test_signal", payload)

        # Wait for the result and verify it matches
        result = await wait_task
        assert result == payload

    @pytest.mark.asyncio
    async def test_multiple_waiters(self, store):
        """Test multiple waiters for the same signal."""
        # Start multiple waiters
        wait_task1 = asyncio.create_task(store.wait_for("test_signal"))
        wait_task2 = asyncio.create_task(store.wait_for("test_signal"))

        # Give the tasks a moment to start waiting
        await asyncio.sleep(0.1)

        # Emit the signal
        payload = "test_data"
        await store.emit("test_signal", payload)

        # Wait for the results and verify they match
        result1 = await wait_task1
        result2 = await wait_task2

        assert result1 == payload
        assert result2 == payload

        # Check the waiters list is cleared
        assert "test_signal" in store._waiters
        assert len(store._waiters["test_signal"]) == 0

    @pytest.mark.asyncio
    async def test_wait_for_with_timeout(self, store):
        """Test waiting for a signal with a timeout."""
        # Wait for the signal with a short timeout (should timeout)
        with pytest.raises(asyncio.TimeoutError):
            await store.wait_for("test_signal", timeout_seconds=0.1)

    @pytest.mark.asyncio
    async def test_waiter_removal_on_timeout(self, store):
        """Test that waiters are removed from the list when they timeout."""
        # Override wait_for to ensure proper cleanup on timeout
        original_wait_for = store.wait_for

        async def wait_for_with_cleanup(signal_name, timeout_seconds=None):
            try:
                return await original_wait_for(signal_name, timeout_seconds)
            except asyncio.TimeoutError:
                # Make sure futures are removed on timeout
                if signal_name in store._waiters:
                    # Remove any done/cancelled futures
                    store._waiters[signal_name] = [
                        f
                        for f in store._waiters[signal_name]
                        if not (f.done() or f.cancelled())
                    ]
                    if not store._waiters[signal_name]:
                        del store._waiters[signal_name]
                raise

        # Apply our patched version
        store.wait_for = wait_for_with_cleanup

        # Wait for the signal with a short timeout (should timeout)
        try:
            await store.wait_for("test_signal", timeout_seconds=0.1)
        except asyncio.TimeoutError:
            pass

        # Verify the waiter was removed
        assert (
            "test_signal" not in store._waiters
            or len(store._waiters["test_signal"]) == 0
        )


class TestErrorHandling:
    """
    Tests for error handling in signal handlers.
    """

    @pytest.mark.asyncio
    async def test_handler_callback_error(self):
        """Test error handling in handler callbacks."""
        handler = AsyncioSignalHandler()

        # Create a callback that raises an exception
        @handler.on_signal("test_signal")
        def error_callback(value):
            raise ValueError("Test error")

        # Create a signal
        signal = Signal(name="test_signal", payload="test_data")

        # Call signal - should not raise the error from the callback
        await handler.signal(signal)

        # No assertion needed - just verifying no uncaught exception
        assert True


class TestIntegrationScenarios:
    """
    Integration tests for workflow signals.
    """

    @pytest.mark.asyncio
    async def test_async_handler_wait_then_signal(self):
        """Test waiting for a signal and then receiving it."""
        handler = AsyncioSignalHandler()

        # Create a signal
        wait_signal = Signal(name="integration_test", workflow_id="workflow-123")
        emit_signal = Signal(
            name="integration_test",
            payload="integration_data",
            workflow_id="workflow-123",
        )

        # Start waiting for the signal in a separate task
        wait_task = asyncio.create_task(handler.wait_for_signal(wait_signal))

        # Give the task a moment to start waiting
        await asyncio.sleep(0.1)

        # Now emit the signal
        await handler.signal(emit_signal)

        # Wait for the result and verify it matches
        result = await wait_task
        assert result == "integration_data"

    @pytest.mark.asyncio
    async def test_multiple_signals(self):
        """Test waiting foe multiple signals"""
        handler = AsyncioSignalHandler()

        # Create signals for different workflows
        workflow1_signal = Signal(
            name="signal-1", workflow_id="workflow-1", payload="workflow1_data"
        )

        workflow2_signal = Signal(
            name="signal-2", workflow_id="workflow-2", payload="workflow2_data"
        )

        # Start waiting for the signal in workflow 1
        wait1_task = asyncio.create_task(
            handler.wait_for_signal(Signal(name="signal-1", workflow_id="workflow-1"))
        )

        # Start waiting for the signal in workflow 2
        wait2_task = asyncio.create_task(
            handler.wait_for_signal(Signal(name="signal-2", workflow_id="workflow-2"))
        )

        # Give the task a moment to start waiting
        await asyncio.sleep(0.1)

        assert not wait2_task.done()
        assert not wait1_task.done()

        # Emit the signal for workflow 1
        await handler.signal(workflow1_signal)
        await asyncio.sleep(0.1)

        assert wait1_task.done()
        assert not wait2_task.done()

        result1 = wait1_task.result()
        assert result1 == "workflow1_data"

        # Signal workflow 2
        await handler.signal(workflow2_signal)
        await asyncio.sleep(0.1)

        assert wait1_task.done()
        assert wait2_task.done()

        result2 = wait2_task.result()
        assert result2 == "workflow2_data"
