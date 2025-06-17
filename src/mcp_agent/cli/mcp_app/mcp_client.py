from contextlib import asynccontextmanager
from enum import Enum
from typing import AsyncGenerator, Generic, Literal
from mcp import ClientSession
from pydantic import AnyUrl, BaseModel

import mcp.types as types

from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_CLIENT_INFO = types.Implementation(name="mcp", version="0.1.0")


class Workflow(BaseModel):
    """A workflow definition that the server is capable of running."""

    name: str
    """A human-readable name for this resource."""
    description: str | None = None
    """A description of what this resource represents."""


class ListWorkflowsRequest(types.PaginatedRequest[types.RequestParams | None]):
    """Sent from the client to request a list of workflows the server has."""

    method: Literal["agents/workflows/list"]
    params: types.RequestParams | None = None


class ListWorkflowsResult(types.PaginatedResult):
    """The server's response to a workflows/list request from the client."""

    workflows: list[Workflow]


class MCPClientSession(ClientSession):
    """MCP Client Session with additional support for mcp-agent functionality."""

    async def list_workflows(
        self, cursor: str | None = None
    ) -> ListWorkflowsResult:
        """Send an agents/workflows/list request."""
        return ListWorkflowsResult(workflows=[])

    # TODO: Figure out how to properly handle request with different transports; send_request is restricted to valid ClientRequest types


class TransportType(Enum):
    """Transport types for MCP client-server communication."""

    SSE = "SSE"
    STREAMABLE_HTTP = "STREAMABLE_HTTP"


class MCPClient:
    """MCP Client for interacting with the MCP App server."""

    def __init__(
        self,
        server_url: AnyUrl,
        api_key: str | None = None,
        transport_type: TransportType = TransportType.STREAMABLE_HTTP,
    ) -> None:
        self._api_key = api_key
        self.server_url = server_url
        self.transport_type = transport_type

    def _create_client(self):
        kwargs = {
            "url": self.server_url,
            "headers": {
                "Authorization": (
                    f"Bearer {self._api_key}" if self._api_key else None
                ),
            },
        }
        if self.transport_type == TransportType.STREAMABLE_HTTP:
            kwargs = {
                **kwargs,
                "terminate_on_close": True,
            }
            return streamablehttp_client(
                **kwargs,
            )
        else:  # SSE
            return sse_client(**kwargs)

    @asynccontextmanager
    async def client_session(self) -> AsyncGenerator[MCPClientSession, None]:
        """Async context manager to create and yield a ClientSession connected to the MCP server."""
        async with self._create_client() as client:
            # Support both 2-tuple and 3-tuple
            if isinstance(client, tuple):
                if len(client) == 2:
                    read_stream, write_stream = client
                elif len(client) == 3:
                    read_stream, write_stream, _ = client
                else:
                    raise ValueError(
                        f"Unexpected tuple length from _create_client: {len(client)}"
                    )
            else:
                # Assume single duplex stream
                read_stream = write_stream = client
            async with MCPClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
