from typing import Protocol, Union
from mcp.types import (
    ElicitRequestFormParams as MCPElicitRequestFormParams,
    ElicitRequestURLParams as MCPElicitRequestURLParams,
    ElicitResult,
    ErrorData,
)


class ElicitRequestFormParams(MCPElicitRequestFormParams):
    """Form mode elicitation request with additional metadata."""

    server_name: str | None = None
    """Name of the MCP server making the elicitation request."""


class ElicitRequestURLParams(MCPElicitRequestURLParams):
    """URL mode elicitation request with additional metadata."""

    server_name: str | None = None
    """Name of the MCP server making the elicitation request."""


ElicitRequestParams = Union[ElicitRequestFormParams, ElicitRequestURLParams]
"""Elicitation request parameters - either form or URL mode, with server_name."""


class ElicitationCallback(Protocol):
    """Protocol for callbacks that handle elicitations."""

    async def __call__(self, request: ElicitRequestParams) -> ElicitResult | ErrorData:
        """Handle a elicitation request.

        Args:
            request (ElicitRequestParams): The elictation request to handle

        Returns:
            ElicitResult | ErrorData: The elicitation response to return back to the MCP server
        """
        ...
