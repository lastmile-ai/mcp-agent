import pytest
from unittest.mock import MagicMock

from mcp_agent.executor.executor import AsyncioExecutor


class RecordingSignalBus:
    """Signal bus stub that returns immediately instead of waiting for a signal."""

    def __init__(self, payload="payload"):
        self.payload = payload

    async def wait_for_signal(self, signal, timeout_seconds=None):
        return self.payload


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.signal_notification = None
    context.tracing_enabled = False
    return context


@pytest.fixture
def executor(mock_context):
    executor = AsyncioExecutor(signal_bus=RecordingSignalBus())
    executor._context = mock_context
    return executor


class TestWaitForSignalNotification:
    @pytest.mark.asyncio
    async def test_async_signal_notification_is_awaited(self, executor, mock_context):
        calls = []

        async def on_signal(**kwargs):
            calls.append(kwargs)

        mock_context.signal_notification = on_signal

        result = await executor.wait_for_signal(
            "human_input",
            request_id="req-1",
            workflow_id="wf-1",
            run_id="run-1",
            signal_description="Need approval",
            timeout_seconds=30,
        )

        assert result == "payload"
        assert len(calls) == 1
        assert calls[0]["signal_name"] == "human_input"
        assert calls[0]["request_id"] == "req-1"
        assert calls[0]["workflow_id"] == "wf-1"
        assert calls[0]["run_id"] == "run-1"
        assert calls[0]["metadata"]["description"] == "Need approval"
        assert calls[0]["metadata"]["timeout_seconds"] == 30

    @pytest.mark.asyncio
    async def test_sync_signal_notification_is_supported(self, executor, mock_context):
        calls = []

        def on_signal(**kwargs):
            calls.append(kwargs)

        mock_context.signal_notification = on_signal

        result = await executor.wait_for_signal("human_input")

        assert result == "payload"
        assert len(calls) == 1
        assert calls[0]["signal_name"] == "human_input"
