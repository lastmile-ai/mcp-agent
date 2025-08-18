from mcp_agent.workflows.swarm.swarm import Swarm
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.tracing.token_tracking_decorator import track_tokens
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class OpenAISwarm(Swarm, OpenAIAugmentedLLM):
    """
    MCP version of the OpenAI Swarm class (https://github.com/openai/swarm.), using OpenAI's ChatCompletion as the LLM.
    """

    @track_tokens(node_type="agent")
    async def generate(self, message, request_params: RequestParams | None = None):
        params = self.get_request_params(
            request_params,
            default=RequestParams(
                model="gpt-4o",
                maxTokens=8192,
                parallel_tool_calls=False,
            ),
        )
        iterations = 0
        response = None
        agent_name = str(self.agent.name) if self.agent else None

        while iterations < params.max_iterations and self.should_continue():
            response = await super().generate(
                message=message
                if iterations == 0
                else "Please resolve my original request. If it has already been resolved then end turn",
                request_params=params.model_copy(
                    update={"max_iterations": 1}  # TODO: saqadri - validate
                ),
            )
            logger.debug(f"Agent: {agent_name}, response:", data=response)
            agent_name = self.agent.name if self.agent else None
            iterations += 1

        # Return final response back
        return response
