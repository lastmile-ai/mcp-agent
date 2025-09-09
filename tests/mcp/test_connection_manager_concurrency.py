import asyncio
import threading

import anyio
import pytest

from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager


class DummyServerRegistry:
    def __init__(self):
        self.registry = {}
        self.init_hooks = {}


@pytest.mark.anyio("asyncio")
async def test_concurrent_close_calls_same_and_cross_thread():
    mgr = MCPConnectionManager(server_registry=DummyServerRegistry())
    await mgr.__aenter__()

    # Run one close() on the event loop and one from a separate thread at the same time
    thread_exc = []

    def close_in_thread():
        async def _run():
            try:
                # Exercise cross-thread shutdown path
                await mgr.close()
            except Exception as e:
                thread_exc.append(e)

        asyncio.run(_run())

    t = threading.Thread(target=close_in_thread, daemon=True)

    async with anyio.create_task_group() as tg:
        # Start cross-thread close, then quickly start same-thread close
        t.start()
        # Add a tiny delay to improve overlap
        await anyio.sleep(0.05)

        async def close_in_loop():
            await mgr.close()

        # Guard against hangs
        with anyio.fail_after(6.0):
            tg.start_soon(close_in_loop)
            # Wait for thread to complete
            await anyio.to_thread.run_sync(t.join)

    # Ensure no exceptions from thread
    assert not thread_exc, f"Thread close failed: {thread_exc!r}"

    # Now exit context to close the owner TaskGroup on the origin loop
    await mgr.__aexit__(None, None, None)

    # Verify TaskGroup cleared
    assert getattr(mgr, "_tg", None) is None
    assert getattr(mgr, "_tg_active", False) is False
