"""
This module defines a `ServerRegistry` class for managing MCP server configurations
and initialization logic.

The class loads server configurations from a YAML file,
supports dynamic registration of initialization hooks, and provides methods for
server initialization.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Callable, Dict, AsyncGenerator, Optional, TYPE_CHECKING

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    stdio_client,
    get_default_environment,
)
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client, MCP_SESSION_ID
from mcp.client.websocket import websocket_client

from mcp_agent.config import (
    get_settings,
    MCPServerAuthSettings,
    MCPServerSettings,
    Settings,
)

from mcp_agent.logging.logger import get_logger
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.mcp.mcp_connection_manager import MCPConnectionManager

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)

InitHookCallable = Callable[[ClientSession | None, MCPServerAuthSettings | None], bool]
"""
A type alias for an initialization hook function that is invoked after MCP server initialization.

Args:
    session (ClientSession | None): The client session for the server connection.
    auth (MCPServerAuthSettings | None): The authentication configuration for the server.

Returns:
    bool: Result of the post-init hook (false indicates failure).
"""


class ServerRegistry:
    """
    A registry for managing server configurations and initialization logic.

    The `ServerRegistry` class is responsible for loading server configurations
    from a YAML file, registering initialization hooks, initializing servers,
    and executing post-initialization hooks dynamically.

    Attributes:
        config_path (str): Path to the YAML configuration file.
        registry (Dict[str, MCPServerSettings]): Loaded server configurations.
        init_hooks (Dict[str, InitHookCallable]): Registered initialization hooks.
    """

    def __init__(self, config: Settings | None = None, config_path: str | None = None):
        """
        Initialize the ServerRegistry with a configuration file.

        Args:
            config (Settings): The Settings object containing the server configurations.
            config_path (str): Path to the YAML configuration file.
        """
        mcp_servers = (
            self.load_registry_from_file(config_path)
            if config is None
            else config.mcp.servers
        )

        # Use default server name if config name not defined
        for server_name in mcp_servers:
            if mcp_servers[server_name].name is None:
                mcp_servers[server_name].name = server_name

        self.registry = mcp_servers
        self.init_hooks: Dict[str, InitHookCallable] = {}
        self.connection_manager = MCPConnectionManager(self)

    def load_registry_from_file(
        self, config_path: str | None = None
    ) -> Dict[str, MCPServerSettings]:
        """
        Load the YAML configuration file and validate it.

        Returns:
            Dict[str, MCPServerSettings]: A dictionary of server configurations.

        Raises:
            ValueError: If the configuration is invalid.
        """

        servers = get_settings(config_path).mcp.servers or {}
        return servers

    @asynccontextmanager
    async def start_server(
        self,
        server_name: str,
        client_session_factory: Callable[
            [
                MemoryObjectReceiveStream,
                MemoryObjectSendStream,
                timedelta | None,
                Optional["Context"],
            ],
            ClientSession,
        ] = ClientSession,
        session_id: str | None = None,
        context: Optional["Context"] = None,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Starts the server process based on its configuration. To initialize, call initialize_server

        Args:
            server_name (str): The name of the server to initialize.

        Returns:
            StdioServerParameters: The server parameters for stdio transport.

        Raises:
            ValueError: If the server is not found or has an unsupported transport.
        """
        if server_name not in self.registry:
            raise ValueError(f"Server '{server_name}' not found in registry.")

        config = self.registry[server_name]

        read_timeout_seconds = (
            timedelta(config.read_timeout_seconds)
            if config.read_timeout_seconds
            else None
        )

        if config.transport == "stdio":
            if not config.command and not config.args:
                raise ValueError(
                    f"Command and args are required for stdio transport: {server_name}"
                )

            server_params = StdioServerParameters(
                command=config.command,
                args=config.args or [],
                env={**get_default_environment(), **(config.env or {})},
            )

            async with stdio_client(server_params) as (read_stream, write_stream):
                # Construct session; tolerate factories that don't accept 'context'
                try:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                        context=context,
                    )
                except TypeError:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                    )
                async with session:
                    logger.info(
                        f"{server_name}: Connected to server using stdio transport."
                    )
                    try:
                        yield session
                    finally:
                        logger.debug(f"{server_name}: Closed session to server")
        elif config.transport in ["streamable_http", "streamable-http", "http"]:
            if not config.url:
                raise ValueError(
                    f"URL is required for Streamable HTTP transport: {server_name}"
                )

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

            # For Streamable HTTP, we get an additional callback for session ID
            async with streamablehttp_client(
                **kwargs,
            ) as (read_stream, write_stream, session_id_callback):
                try:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                        context=context,
                    )
                except TypeError:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                    )

                if session_id_callback and isinstance(session, MCPAgentClientSession):
                    session.set_session_id_callback(session_id_callback)
                    logger.debug(f"{server_name}: Session ID tracking enabled")

                async with session:
                    logger.info(
                        f"{server_name}: Connected to server using Streamable HTTP transport."
                    )
                    try:
                        yield session
                    finally:
                        logger.debug(f"{server_name}: Closed session to server")

        elif config.transport == "sse":
            if not config.url:
                raise ValueError(f"URL is required for SSE transport: {server_name}")

            kwargs = {
                "url": config.url,
                "headers": config.headers,
            }

            if config.http_timeout_seconds:
                kwargs["timeout"] = config.http_timeout_seconds

            if config.read_timeout_seconds:
                kwargs["sse_read_timeout"] = config.read_timeout_seconds

            # Use sse_client to get the read and write streams
            async with sse_client(**kwargs) as (
                read_stream,
                write_stream,
            ):
                try:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                        context=context,
                    )
                except TypeError:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                    )
                async with session:
                    logger.info(
                        f"{server_name}: Connected to server using SSE transport."
                    )
                    try:
                        yield session
                    finally:
                        logger.debug(f"{server_name}: Closed session to server")

        elif config.transport == "websocket":
            if not config.url:
                raise ValueError(
                    f"URL is required for websocket transport: {server_name}"
                )

            async with websocket_client(url=config.url) as (  # pylint: disable=W0135
                read_stream,
                write_stream,
            ):
                try:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                        context=context,
                    )
                except TypeError:
                    session = client_session_factory(
                        read_stream,
                        write_stream,
                        read_timeout_seconds,
                    )
                async with session:
                    logger.info(
                        f"{server_name}: Connected to server using websocket transport."
                    )
                    try:
                        yield session
                    finally:
                        logger.debug(f"{server_name}: Closed session to server")
        # Unsupported transport
        else:
            raise ValueError(f"Unsupported transport: {config.transport}")

    @asynccontextmanager
    async def initialize_server(
        self,
        server_name: str,
        client_session_factory: Callable[
            [
                MemoryObjectReceiveStream,
                MemoryObjectSendStream,
                timedelta | None,
                Optional["Context"],
            ],
            ClientSession,
        ] = ClientSession,
        init_hook: InitHookCallable = None,
        session_id: str | None = None,
        context: Optional["Context"] = None,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Initialize a server based on its configuration.
        After initialization, also calls any registered or provided initialization hook for the server.

        Args:
            server_name (str): The name of the server to initialize.
            init_hook (InitHookCallable): Optional initialization hook function to call after initialization.

        Returns:
            StdioServerParameters: The server parameters for stdio transport.

        Raises:
            ValueError: If the server is not found or has an unsupported transport.
        """

        if server_name not in self.registry:
            raise ValueError(f"Server '{server_name}' not found in registry.")

        config = self.registry[server_name]

        async with self.start_server(
            server_name,
            client_session_factory=client_session_factory,
            session_id=session_id,
            context=context,
        ) as session:
            try:
                logger.info(f"{server_name}: Initializing server...")
                await session.initialize()
                logger.info(f"{server_name}: Initialized.")

                intialization_callback = (
                    init_hook
                    if init_hook is not None
                    else self.init_hooks.get(server_name)
                )

                if intialization_callback:
                    logger.info(f"{server_name}: Executing init hook")
                    intialization_callback(session, config.auth)

                logger.info(f"{server_name}: Up and running!")
                yield session
            finally:
                logger.info(f"{server_name}: Ending server session.")

    def register_init_hook(self, server_name: str, hook: InitHookCallable) -> None:
        """
        Register an initialization hook for a specific server. This will get called
        after the server is initialized.

        Args:
            server_name (str): The name of the server.
            hook (callable): The initialization function to register.
        """
        if server_name not in self.registry:
            raise ValueError(f"Server '{server_name}' not found in registry.")

        self.init_hooks[server_name] = hook

    def execute_init_hook(self, server_name: str, session=None) -> bool:
        """
        Execute the initialization hook for a specific server.

        Args:
            server_name (str): The name of the server.
            session: The session object to pass to the initialization hook.
        """
        if server_name in self.init_hooks:
            hook = self.init_hooks[server_name]
            config = self.registry[server_name]
            logger.info(f"Executing init hook for '{server_name}'")
            return hook(session, config.auth)
        else:
            logger.info(f"No init hook registered for '{server_name}'")

    def get_server_config(self, server_name: str) -> MCPServerSettings | None:
        """
        Get the configuration for a specific server.

        Args:
            server_name (str): The name of the server.

        Returns:
            MCPServerSettings: The server configuration.
        """
        server_config = self.registry.get(server_name)
        if server_config is None:
            logger.warning(f"Server '{server_name}' not found in registry.")
            return None
        elif server_config.name is None:
            server_config.name = server_name
        return server_config
