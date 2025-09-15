from contextlib import asynccontextmanager
from datetime import timedelta
from typing import AsyncGenerator, Callable, Optional

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession

from mcp_agent.logging.logger import get_logger
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.mcp.mcp_agent_client_session import MCPAgentClientSession
from mcp_agent.core.context import Context

logger = get_logger(__name__)


@asynccontextmanager
async def gen_client(
    server_name: str,
    server_registry: ServerRegistry,
    client_session_factory: Callable[
        [
            MemoryObjectReceiveStream,
            MemoryObjectSendStream,
            timedelta | None,
            Optional[Context],
        ],
        ClientSession,
    ] = MCPAgentClientSession,
    session_id: str | None = None,
    context: Optional[Context] = None,
) -> AsyncGenerator[ClientSession, None]:
    """
    Create a client session to the specified server.
    Handles server startup, initialization, and message receive loop setup.
    If required, callers can specify their own message receive loop and ClientSession class constructor to customize further.
    For persistent connections, use connect() or MCPConnectionManager instead.
    """
    if not server_registry:
        raise ValueError(
            "Server registry not found in the context. Please specify one either on this method, or in the context."
        )

    async with server_registry.initialize_server(
        server_name=server_name,
        client_session_factory=client_session_factory,
        session_id=session_id,
        context=context,
    ) as session:
        yield session


async def connect(
    server_name: str,
    server_registry: ServerRegistry,
    client_session_factory: Callable[
        [
            MemoryObjectReceiveStream,
            MemoryObjectSendStream,
            timedelta | None,
            Optional[Context],
        ],
        ClientSession,
    ] = MCPAgentClientSession,
    session_id: str | None = None,
    context: Optional[Context] = None,
) -> ClientSession:
    """
    Create a persistent client session to the specified server.
    Handles server startup, initialization, and message receive loop setup.
    If required, callers can specify their own message receive loop and ClientSession class constructor to customize further.
    """
    if not server_registry:
        raise ValueError(
            "Server registry not found in the context. Please specify one either on this method, or in the context."
        )

    server_connection = await server_registry.connection_manager.get_server(
        server_name=server_name,
        client_session_factory=client_session_factory,
        session_id=session_id,
    )

    return server_connection.session


async def disconnect(
    server_name: str | None,
    server_registry: ServerRegistry,
) -> None:
    """
    Disconnect from the specified server. If server_name is None, disconnect from all servers.
    """
    if not server_registry:
        raise ValueError(
            "Server registry not found in the context. Please specify one either on this method, or in the context."
        )

    if server_name:
        await server_registry.connection_manager.disconnect_server(
            server_name=server_name
        )
    else:
        await server_registry.connection_manager.disconnect_all()
