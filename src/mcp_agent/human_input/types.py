from typing import Any, Protocol
from pydantic import BaseModel

HUMAN_INPUT_SIGNAL_NAME = "__human_input__"


class HumanInputRequest(BaseModel):
    """Represents a request for human input."""

    prompt: str
    """The prompt to show to the user"""

    description: str | None = None
    """Optional description of what the input is for"""

    request_id: str | None = None
    """Unique identifier for this request"""

    workflow_id: str | None = None
    """Optional workflow ID if using workflow engine"""

    run_id: str | None = None
    """Optional run ID if using workflow engine"""

    timeout_seconds: int | None = None
    """Optional timeout in seconds"""

    metadata: dict | None = None
    """Additional request payload"""


class HumanInputResponse(BaseModel):
    """Represents a response to a human input request"""

    request_id: str
    """ID of the original request"""

    response: str
    """The input provided by the human"""

    metadata: dict[str, Any] | None = None
    """Additional response payload"""


class HumanInputCallback(Protocol):
    """Protocol for callbacks that handle human input requests."""

    async def __call__(self, request: HumanInputRequest) -> HumanInputResponse:
        """
        Handle a human input request.

        Args:
            request: The input request to handle

        Returns:
            The response from the human input
        """
        ...
