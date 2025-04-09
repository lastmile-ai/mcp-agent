"""
Manages the lifecycle of multiple MCP server connections.
"""

from datetime import timedelta
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
from mcp.types import JSONRPCMessage, ServerCapabilities

from mcp_agent.config import MCPServerSettings
from mcp_agent.core.exceptions import ServerInitializationError
from mcp_agent.event_progress import ProgressAction
from mcp_agent.logging.logger import get_logger
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.mcp.stdio import stdio_client_with_rich_stderr
from mcp_agent.mcp.websocket import websocket_client
from mcp_agent.context_dependent import ContextDependent

if TYPE_CHECKING:
    from mcp_agent.mcp_server_registry import InitHookCallable, ServerRegistry
    from mcp_agent.context import Context

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

        async with transport_context as (read_stream, write_stream):
            # Build a session
            server_conn.create_session(read_stream, write_stream)

            async with server_conn.session:
                # Initialize the session
                await server_conn.initialize_session()

                # Wait until we're asked to shut down
                await server_conn.wait_for_shutdown_request()

    except Exception as exc:
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

    async def __aenter__(self):
        # We create a task group to manage all server lifecycle tasks
        tg = create_task_group()
        # Enter the task group context
        await tg.__aenter__()
        self._tg_active = True
        self._tg = tg
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure clean shutdown of all connections before exiting."""
        try:
            # First request all servers to shutdown
            logger.debug("MCPConnectionManager: shutting down all server tasks...")
            await self.disconnect_all()

            # TODO: saqadri (FA1) - Is this needed?
            # Add a small delay to allow for clean shutdown
            await anyio.sleep(0.5)

            # Then close the task group if it's active
            if self._tg_active:
                await self._tg.__aexit__(exc_type, exc_val, exc_tb)
                self._tg_active = False
                self._tg = None
        except AttributeError:  # Handle missing `_exceptions`
            pass
        except Exception as e:
            logger.error(f"MCPConnectionManager: Error during shutdown: {e}")

    async def launch_server(
        self,
        server_name: str,
        client_session_factory: Callable[
            [MemoryObjectReceiveStream, MemoryObjectSendStream, timedelta | None],
            ClientSession,
        ],
        init_hook: Optional["InitHookCallable"] = None,
    ) -> ServerConnection:
        """
        Connect to a server and return a RunningServer instance that will persist
        until explicitly disconnected.
        """
        # Create task group if it doesn't exist yet - make this method more resilient
        if not self._tg_active:
            tg = create_task_group()
            await tg.__aenter__()
            self._tg_active = True
            self._tg = tg
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
                    args=config.args,
                    env={**get_default_environment(), **(config.env or {})},
                )
                # Create stdio client config with redirected stderr
                return stdio_client_with_rich_stderr(server_params)
            elif config.transport == "sse":
                return sse_client(config.url, config.headers)
            elif config.transport == "websocket":
                return websocket_client(config.url, config.headers)
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
        client_session_factory: Callable,
        init_hook: Optional["InitHookCallable"] = None,
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

        logger.info("All persistent server connections signaled to disconnect.")
