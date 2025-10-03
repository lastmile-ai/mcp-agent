import asyncio
from dataclasses import dataclass
from typing import Generic, TypeVar

from mcp_agent.executor.workflow import Workflow
from mcp_agent.human_input.types import HumanInputRequest, HumanInputResponse
from mcp_agent.logging.logger import get_logger

from temporalio import workflow

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class HumanResponse:
    response: str


class InteractiveWorkflow(Workflow[T], Generic[T]):
    """
    A workflow with support for handling human input requests and responses.

    Example:
        To use this workflow, create a workflow like this:

        @app.workflow
        class MyWorkflow(InteractiveWorkflow):
            @app.workflow_run
            async def run(self, input: str) -> WorkflowResult[str]:
                interactive_agent = Agent(
                    name="basic_interactive_agent",
                    instruction="You are a helpful assistant that can interact with the user.",
                    human_input_callback=self.create_input_callback(), # <--- this enables human input handling
                )

                # etc.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lock = asyncio.Lock()
        self._request: HumanInputRequest = None
        self._response: str = None

    @workflow.query
    def get_human_input_request(self) -> str:
        """
        A query returning the current human input request as a JSON string, if any.
        """
        if self._request is None:
            return "{}"
        return self._request.model_dump_json(include={"prompt", "description"})

    @workflow.signal
    async def provide_human_input(self, input: HumanResponse) -> None:
        """
        Signal to set the human input response.
        """
        async with self._lock:
            self._request = None
            self._response = input.response.strip()

    def create_input_callback(self) -> callable:
        """
        Create a callback function that can be used to handle human input requests.
        """

        async def input_callback(request: HumanInputRequest) -> HumanInputResponse:
            self._response = None
            self._request = request

            await workflow.wait_condition(lambda: self._response is not None)

            if self._response is None:
                logger.warning("Input request timed out")
                return HumanInputResponse(request_id=request.request_id, response="")

            return HumanInputResponse(
                request_id=request.request_id, response=self._response
            )

        return input_callback
