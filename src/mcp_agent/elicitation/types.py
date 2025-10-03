from typing import Protocol
from mcp.types import (
    ElicitRequestParams as MCPElicitRequestParams,
    ElicitResult,
    ErrorData,
)


class ElicitRequestParams(MCPElicitRequestParams):
    server_name: str | None = None
    """Name of the MCP server making the elicitation request"""


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
