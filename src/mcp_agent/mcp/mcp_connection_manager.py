"""
Manages the lifecycle of multiple MCP server connections.
"""

from datetime import timedelta
import asyncio
import threading
from typing import (
    AsyncGenerator,
    Callable,
    Dict,
    Optional,
    TYPE_CHECKING,
)

import anyio
from anyio import Event, create_task_group, Lock
from anyio.abc import TaskGroup
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from mcp import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    get_default_environment,
)
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client, MCP_SESSION_ID
from mcp.client.websocket import websocket_client
from mcp.types import JSONRPCMessage, ServerCapabilities

from mcp_agent.config import MCPServerSettings
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.core.exceptions import ServerInitializationError
from mcp_agent.logging.event_progress import ProgressAction
from mcp_agent.logging.logger import get_logger
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession

if TYPE_CHECKING:
    from mcp_agent.mcp.mcp_server_registry import InitHookCallable, ServerRegistry
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class ServerConnection:
    """
    Represents a long-lived MCP server connection, including:
    - The ClientSession to the server
    - The transport streams (via stdio/sse, etc.)
    """

    def __init__(
        self,
        server_name: str,
        server_config: MCPServerSettings,
        transport_context_factory: Callable[
            [],
            AsyncGenerator[
                tuple[
                    MemoryObjectReceiveStream[JSONRPCMessage | Exception],
                    MemoryObjectSendStream[JSONRPCMessage],
                ],
                None,
            ],
        ],
        client_session_factory: Callable[
            [MemoryObjectReceiveStream, MemoryObjectSendStream, timedelta | None],
            ClientSession,
        ],
        init_hook: Optional["InitHookCallable"] = None,
    ):
        self.server_name = server_name
        self.server_config = server_config
        self.server_capabilities: ServerCapabilities | None = None
        self.session: ClientSession | None = None
        self._client_session_factory = client_session_factory
        self._init_hook = init_hook
        self._transport_context_factory = transport_context_factory
        # Signal that session is fully up and initialized
        self._initialized_event = Event()

        # Signal we want to shut down
        self._shutdown_event = Event()

        # Track error state
        self._error: bool = False
        self._error_message: str | None = None

    def is_healthy(self) -> bool:
        """Check if the server connection is healthy and ready to use."""
        return self.session is not None and not self._error

    def reset_error_state(self) -> None:
        """Reset the error state, allowing reconnection attempts."""
        self._error = False
        self._error_message = None

    def request_shutdown(self) -> None:
        """
        Request the server to shut down. Signals the server lifecycle task to exit.
        """
        self._shutdown_event.set()

    # Back-compat helper to avoid tests reaching into Event internals across threads
    def _is_shutdown_requested_flag(self) -> bool:
        """Return True if a shutdown has been requested for this server connection."""
        return self._shutdown_event.is_set()

    async def wait_for_shutdown_request(self) -> None:
        """
        Wait until the shutdown event is set.
        """
        await self._shutdown_event.wait()

    async def initialize_session(self) -> None:
        """
        Initializes the server connection and session.
        Must be called within an async context.
        """

        result = await self.session.initialize()

        self.server_capabilities = result.capabilities
        # If there's an init hook, run it
        if self._init_hook:
            logger.info(f"{self.server_name}: Executing init hook.")
            self._init_hook(self.session, self.server_config.auth)

        # Now the session is ready for use
        self._initialized_event.set()

    async def wait_for_initialized(self) -> None:
        """
        Wait until the session is fully initialized.
        """
        await self._initialized_event.wait()

    def create_session(
        self,
        read_stream: MemoryObjectReceiveStream,
        send_stream: MemoryObjectSendStream,
    ) -> ClientSession:
        """
        Create a new session instance for this server connection.
        """

        read_timeout = (
            timedelta(seconds=self.server_config.read_timeout_seconds)
            if self.server_config.read_timeout_seconds
            else None
        )

        session = self._client_session_factory(read_stream, send_stream, read_timeout)

        # Make the server config available to the session for initialization
        if hasattr(session, "server_config"):
            session.server_config = self.server_config

        self.session = session

        return session


async def _server_lifecycle_task(server_conn: ServerConnection) -> None:
    """
    Manage the lifecycle of a single server connection.
    Runs inside the MCPConnectionManager's shared TaskGroup.
    """
    server_name = server_conn.server_name
    try:
        transport_context = server_conn._transport_context_factory()

        async with transport_context as (read_stream, write_stream, *extras):
            # If the transport provides a session ID callback (streamable_http does),
            # store it in the server connection
            if (
                len(extras) > 0
                and callable(extras[0])
                and isinstance(server_conn.session, MCPAgentClientSession)
            ):
                server_conn.session.set_session_id_callback(extras[0])

            # Build a session
            server_conn.create_session(read_stream, write_stream)

            async with server_conn.session:
                # Initialize the session
                await server_conn.initialize_session()

                # Wait until we're asked to shut down
                await server_conn.wait_for_shutdown_request()
    except Exception as exc:
        import traceback

        if hasattr(
            exc, "exceptions"
        ):  # ExceptionGroup or BaseExceptionGroup in Python 3.11+
            for i, subexc in enumerate(exc.exceptions):
                tb_lines = traceback.format_exception(
                    type(subexc), subexc, subexc.__traceback__
                )
                logger.error(
                    f"{server_name}: Sub-error {i + 1} in lifecycle task:\n{''.join(tb_lines)}"
                )
        else:
            logger.error(
                f"{server_name}: Lifecycle task encountered an error: {exc}",
                exc_info=True,
                data={
                    "progress_action": ProgressAction.FATAL_ERROR,
                    "server_name": server_name,
                },
            )

        server_conn._error = True
        server_conn._error_message = str(exc)
        # If there's an error, we should also set the event so that
        # 'get_server' won't hang
        server_conn._initialized_event.set()
        # No raise - allow graceful exit


class MCPConnectionManager(ContextDependent):
    """
    Manages the lifecycle of multiple MCP server connections.
    """

    def __init__(
        self, server_registry: "ServerRegistry", context: Optional["Context"] = None
    ):
        super().__init__(context)
        self.server_registry = server_registry
        self.running_servers: Dict[str, ServerConnection] = {}
        self._lock = Lock()
        # Manage our own task group - independent of task context
        self._tg: TaskGroup | None = None
        self._tg_active = False
        # Track the thread this manager was created in to ensure TaskGroup cleanup
        self._thread_id = threading.get_ident()
        # Event loop where the TaskGroup lives
        self._loop: asyncio.AbstractEventLoop | None = None
        # Owner task + coordination events for safe TaskGroup lifecycle
        self._tg_owner_task: asyncio.Task | None = None
        self._owner_tg: TaskGroup | None = None
        self._tg_ready_event: Event = Event()
        self._tg_close_event: Event = Event()
        self._tg_closed_event: Event = Event()
        # Ensure a single close sequence at a time on the origin loop
        self._close_lock = Lock()
        # Serialize owner startup to avoid races across tasks
        self._owner_start_lock = Lock()

    async def __aenter__(self):
        # Start the TaskGroup owner task and wait until ready
        await self._start_owner()
        # Record the loop and thread where the TaskGroup is running
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure clean shutdown of all connections before exiting."""
        await self.close(exc_type, exc_val, exc_tb)
        # Close the owner TaskGroup in the same task that entered it
        if self._owner_tg is not None:
            try:
                await self._owner_tg.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.warning(
                    f"MCPConnectionManager: Error during owner TaskGroup cleanup: {e}"
                )
            finally:
                self._owner_tg = None

    async def close(self, exc_type=None, exc_val=None, exc_tb=None):
        """Close all connections and tear down the internal TaskGroup safely.

        This is thread-aware: if called from a different thread than the one where the
        TaskGroup was created, it will signal the owner task on the original loop to
        perform cleanup and await completion without violating task affinity.
        """
        try:
            current_thread = threading.get_ident()
            if current_thread == self._thread_id:
                # Same thread: perform shutdown inline with exclusive access
                async with self._close_lock:
                    logger.debug(
                        "MCPConnectionManager: shutting down all server tasks..."
                    )
                    await self.disconnect_all()
                    await anyio.sleep(0.5)
                    if self._tg_active:
                        self._tg_close_event.set()
                        # Wait for owner to report TaskGroup closed with an anyio timeout
                        try:
                            with anyio.fail_after(5.0):
                                await self._tg_closed_event.wait()
                        except TimeoutError:
                            logger.warning(
                                "MCPConnectionManager: Timeout waiting for TaskGroup owner to close"
                            )
                # Do not attempt to close the owner TaskGroup here; __aexit__ will handle it
            else:
                # Different thread – run entire shutdown on the original loop to avoid cross-thread Event.set
                if self._loop is not None:

                    async def _shutdown_and_close():
                        logger.debug(
                            "MCPConnectionManager: shutting down all server tasks (origin loop)..."
                        )
                        async with self._close_lock:
                            await self.disconnect_all()
                            await anyio.sleep(0.5)
                            if self._tg_active:
                                self._tg_close_event.set()
                                await self._tg_closed_event.wait()

                    try:
                        cfut = asyncio.run_coroutine_threadsafe(
                            _shutdown_and_close(), self._loop
                        )
                        # Wait in a worker thread to avoid blocking non-asyncio contexts
                        try:
                            with anyio.fail_after(5.0):
                                await anyio.to_thread.run_sync(cfut.result)
                        except TimeoutError:
                            logger.warning(
                                "MCPConnectionManager: Timeout during cross-thread shutdown/close"
                            )
                            try:
                                cfut.cancel()
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(
                            f"MCPConnectionManager: Error scheduling cross-thread shutdown: {e}"
                        )
                else:
                    logger.warning(
                        "MCPConnectionManager: No event loop recorded for cleanup; skipping TaskGroup close"
                    )
        except AttributeError:  # Handle missing `_exceptions`
            pass
        except Exception as e:
            logger.warning(f"MCPConnectionManager: Error during shutdown: {e}")

    async def _start_owner(self):
        """Start the TaskGroup owner task if not already running (task-safe)."""
        async with self._owner_start_lock:
            # If an owner is active or TaskGroup is already active, nothing to do
            if (self._tg_owner_task and not self._tg_owner_task.done()) or (
                self._tg_active and self._tg is not None
            ):
                return
            # If previous owner exists but is done (possibly with error), log and restart
            if self._tg_owner_task and self._tg_owner_task.done():
                try:
                    exc = self._tg_owner_task.exception()
                    if exc:
                        logger.warning(
                            f"MCPConnectionManager: restarting owner after error: {exc}"
                        )
                except Exception:
                    logger.warning(
                        "MCPConnectionManager: restarting owner after unknown state"
                    )
            # Reset coordination events (safe here since no active owner/TG)
            self._tg_ready_event = Event()
            self._tg_close_event = Event()
            self._tg_closed_event = Event()
            # Record loop and thread
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            self._thread_id = threading.get_ident()
            # Create an owner TaskGroup and start the owner task within it
            owner_tg = create_task_group()
            await owner_tg.__aenter__()
            self._owner_tg = owner_tg
            owner_tg.start_soon(self._tg_owner)
            # Wait until the TaskGroup is ready
            await self._tg_ready_event.wait()

    async def _tg_owner(self):
        """Own the TaskGroup lifecycle so __aexit__ runs in the same task it was entered."""
        try:
            async with create_task_group() as tg:
                self._tg = tg
                self._tg_active = True
                # Signal that TaskGroup is ready
                self._tg_ready_event.set()
                # Wait for close request
                await self._tg_close_event.wait()
        except Exception as e:
            logger.warning(f"MCPConnectionManager: Error in TaskGroup owner: {e}")
        finally:
            # Mark closed and clear references
            self._tg_active = False
            self._tg = None
            # Signal that TaskGroup has been closed
            try:
                self._tg_closed_event.set()
            except Exception as e:
                logger.warning(f"Failed to set _tg_closed_event: {e}")

    async def launch_server(
        self,
        server_name: str,
        client_session_factory: Callable[
            [MemoryObjectReceiveStream, MemoryObjectSendStream, timedelta | None],
            ClientSession,
        ],
        init_hook: Optional["InitHookCallable"] = None,
        session_id: str | None = None,
    ) -> ServerConnection:
        """
        Connect to a server and return a RunningServer instance that will persist
        until explicitly disconnected.
        """
        # Ensure the TaskGroup owner is running - make this method more resilient
        if not self._tg_active:
            await self._start_owner()
            logger.info(
                f"MCPConnectionManager: Auto-created task group for server: {server_name}"
            )

        config = self.server_registry.registry.get(server_name)
        if not config:
            raise ValueError(f"Server '{server_name}' not found in registry.")

        logger.debug(
            f"{server_name}: Found server configuration=", data=config.model_dump()
        )

        def transport_context_factory():
            if config.transport == "stdio":
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args or [],
                    env={**get_default_environment(), **(config.env or {})},
                )
                # Create stdio client config with redirected stderr
                return stdio_client(server=server_params)
            elif config.transport in ["streamable_http", "streamable-http", "http"]:
                if session_id:
                    headers = config.headers.copy() if config.headers else {}
                    headers[MCP_SESSION_ID] = session_id
                else:
                    headers = config.headers

                kwargs = {
                    "url": config.url,
                    "headers": headers,
                    "terminate_on_close": config.terminate_on_close,
                }

                timeout = (
                    timedelta(seconds=config.http_timeout_seconds)
                    if config.http_timeout_seconds
                    else None
                )

                if timeout is not None:
                    kwargs["timeout"] = timeout

                sse_read_timeout = (
                    timedelta(seconds=config.read_timeout_seconds)
                    if config.read_timeout_seconds
                    else None
                )

                if sse_read_timeout is not None:
                    kwargs["sse_read_timeout"] = sse_read_timeout

                return streamablehttp_client(
                    **kwargs,
                )
            elif config.transport == "sse":
                kwargs = {
                    "url": config.url,
                    "headers": config.headers,
                }

                if config.http_timeout_seconds:
                    kwargs["timeout"] = config.http_timeout_seconds

                if config.read_timeout_seconds:
                    kwargs["sse_read_timeout"] = config.read_timeout_seconds

                return sse_client(**kwargs)
            elif config.transport == "websocket":
                return websocket_client(url=config.url)
            else:
                raise ValueError(f"Unsupported transport: {config.transport}")

        server_conn = ServerConnection(
            server_name=server_name,
            server_config=config,
            transport_context_factory=transport_context_factory,
            client_session_factory=client_session_factory,
            init_hook=init_hook or self.server_registry.init_hooks.get(server_name),
        )

        async with self._lock:
            # Check if already running
            if server_name in self.running_servers:
                return self.running_servers[server_name]

            self.running_servers[server_name] = server_conn
            self._tg.start_soon(_server_lifecycle_task, server_conn)

        logger.info(f"{server_name}: Up and running with a persistent connection!")
        return server_conn

    async def get_server(
        self,
        server_name: str,
        client_session_factory: Callable[
            [MemoryObjectReceiveStream, MemoryObjectSendStream, timedelta | None],
            ClientSession,
        ] = MCPAgentClientSession,
        init_hook: Optional["InitHookCallable"] = None,
        session_id: str | None = None,
    ) -> ServerConnection:
        """
        Get a running server instance, launching it if needed.
        """
        # Get the server connection if it's already running and healthy
        async with self._lock:
            server_conn = self.running_servers.get(server_name)
            if server_conn and server_conn.is_healthy():
                return server_conn
            # If server exists but isn't healthy, remove it so we can create a new one
            if server_conn:
                logger.info(
                    f"{server_name}: Server exists but is unhealthy, recreating..."
                )
                self.running_servers.pop(server_name)
                server_conn.request_shutdown()

        # Launch the connection
        server_conn = await self.launch_server(
            server_name=server_name,
            client_session_factory=client_session_factory,
            init_hook=init_hook,
            session_id=session_id,
        )

        # Wait until it's fully initialized, or an error occurs
        await server_conn.wait_for_initialized()

        # Check if the server is healthy after initialization
        if not server_conn.is_healthy():
            error_msg = server_conn._error_message or "Unknown error"
            raise ServerInitializationError(
                f"MCP Server: '{server_name}': Failed to initialize with error: '{error_msg}'. Check mcp_agent.config.yaml"
            )

        return server_conn

    async def get_server_capabilities(
        self,
        server_name: str,
        client_session_factory: Callable[
            [MemoryObjectReceiveStream, MemoryObjectSendStream, timedelta | None],
            ClientSession,
        ] = MCPAgentClientSession,
    ) -> ServerCapabilities | None:
        """Get the capabilities of a specific server."""
        server_conn = await self.get_server(
            server_name, client_session_factory=client_session_factory
        )
        return server_conn.server_capabilities if server_conn else None

    async def disconnect_server(self, server_name: str) -> None:
        """
        Disconnect a specific server if it's running under this connection manager.
        """
        logger.info(f"{server_name}: Disconnecting persistent connection to server...")

        async with self._lock:
            server_conn = self.running_servers.pop(server_name, None)
        if server_conn:
            server_conn.request_shutdown()
            logger.info(
                f"{server_name}: Shutdown signal sent (lifecycle task will exit)."
            )
        else:
            logger.info(
                f"{server_name}: No persistent connection found. Skipping server shutdown"
            )

    async def disconnect_all(self) -> None:
        """
        Disconnect all servers that are running under this connection manager.
        """
        logger.info("Disconnecting all persistent server connections...")

        # Get a copy of servers to shutdown
        servers_to_shutdown = []

        async with self._lock:
            if not self.running_servers:
                return

            # Make a copy of the servers to shut down
            servers_to_shutdown = list(self.running_servers.items())
            # Clear the dict immediately to prevent any new access
            self.running_servers.clear()

        # Release the lock before waiting for servers to shut down
        for name, conn in servers_to_shutdown:
            logger.info(f"{name}: Requesting shutdown...")
            conn.request_shutdown()

        # Allow some time for transports to clean up if we actually shut anything down
        if servers_to_shutdown:
            await anyio.sleep(0.2)

        logger.info("All persistent server connections signaled to disconnect.")
