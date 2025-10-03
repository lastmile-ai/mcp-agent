from typing import Callable, Dict, Generic, List, Optional, TYPE_CHECKING
from collections import defaultdict

from pydantic import AnyUrl, BaseModel, ConfigDict
from mcp.types import (
    CallToolRequest,
    EmbeddedResource,
    CallToolResult,
    TextContent,
    TextResourceContents,
    Tool,
)

from mcp_agent.agents.agent import Agent
from mcp_agent.human_input.types import HumanInputCallback
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    MessageParamT,
    MessageT,
)
from mcp_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class AgentResource(EmbeddedResource):
    """
    A resource that returns an agent. Meant for use with tool calls that want to return an Agent for further processing.
    """

    agent: Optional["Agent"] = None

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class AgentFunctionResultResource(EmbeddedResource):
    """
    A resource that returns an AgentFunctionResult.
    Meant for use with tool calls that return an AgentFunctionResult for further processing.
    """

    result: "AgentFunctionResult"

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


def create_agent_resource(agent: "Agent") -> AgentResource:
    return AgentResource(
        type="resource",
        agent=agent,
        resource=TextResourceContents(
            text=f"You are now Agent '{agent.name}'. Please review the messages and continue execution",
            uri=AnyUrl("http://fake.url"),  # Required property but not needed
        ),
    )


def create_agent_function_result_resource(
    result: "AgentFunctionResult",
) -> AgentFunctionResultResource:
    return AgentFunctionResultResource(
        type="resource",
        result=result,
        resource=TextResourceContents(
            text=result.value or result.agent.name or "AgentFunctionResult",
            uri=AnyUrl("http://fake.url"),  # Required property but not needed
        ),
    )


class SwarmAgent(Agent):
    """
    A SwarmAgent is an Agent that can spawn other agents and interactively resolve a task.
    Based on OpenAI Swarm: https://github.com/openai/swarm.

    SwarmAgents have access to tools available on the servers they are connected to, but additionally
    have a list of (possibly local) functions that can be called as tools.
    """

    def __init__(
        self,
        name: str,
        instruction: str | Callable[[Dict], str] = "You are a helpful agent.",
        server_names: list[str] = None,
        functions: List["AgentFunctionCallable"] = None,
        parallel_tool_calls: bool = False,
        human_input_callback: HumanInputCallback = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        if server_names is None:
            server_names = []
        if functions is None:
            functions = []

        super().__init__(
            name=name,
            instruction=instruction,
            server_names=server_names,
            functions=functions,
            # TODO: saqadri - figure out if Swarm can maintain connection persistence
            # It's difficult because we don't know when the agent will be done with its task
            connection_persistence=False,
            human_input_callback=human_input_callback,
            context=context,
            **kwargs,
        )
        self.parallel_tool_calls = parallel_tool_calls

    async def call_tool(
        self, name: str, arguments: dict | None = None
    ) -> CallToolResult:
        if not self.initialized:
            await self.initialize()

        if name in self._function_tool_map:
            tool = self._function_tool_map[name]
            result = await tool.run(arguments)

            logger.debug(f"Function tool {name} result:", data=result)

            if isinstance(result, Agent) or isinstance(result, SwarmAgent):
                resource = create_agent_resource(result)
                return CallToolResult(content=[resource])
            elif isinstance(result, AgentFunctionResult):
                resource = create_agent_function_result_resource(result)
                return CallToolResult(content=[resource])
            elif isinstance(result, str):
                # TODO: saqadri - this is likely meant for returning context variables
                return CallToolResult(content=[TextContent(type="text", text=result)])
            elif isinstance(result, dict):
                return CallToolResult(
                    content=[TextContent(type="text", text=str(result))]
                )
            else:
                logger.warning(f"Unknown result type: {result}, returning as text.")
                return CallToolResult(
                    content=[TextContent(type="text", text=str(result))]
                )

        return await super().call_tool(name, arguments)


class AgentFunctionResult(BaseModel):
    """
    Encapsulates the possible return values for a Swarm agent function.

    Attributes:
        value (str): The result value as a string.
        agent (Agent): The agent instance, if applicable.
        context_variables (dict): A dictionary of context variables.
    """

    value: str = ""
    agent: Agent | None = None
    context_variables: dict = {}

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


AgentFunctionReturnType = str | Agent | dict | AgentFunctionResult
"""A type alias for the return type of a Swarm agent function."""

AgentFunctionCallable = Callable[[], AgentFunctionReturnType]


async def create_transfer_to_agent_tool(
    agent: "Agent", agent_function: Callable[[], None]
) -> Tool:
    return Tool(
        name="transfer_to_agent",
        description="Transfer control to the agent",
        agent_resource=create_agent_resource(agent),
        agent_function=agent_function,
    )


async def create_agent_function_tool(agent_function: "AgentFunctionCallable") -> Tool:
    return Tool(
        name="agent_function",
        description="Agent function",
        agent_resource=None,
        agent_function=agent_function,
    )


class Swarm(AugmentedLLM[MessageParamT, MessageT], Generic[MessageParamT, MessageT]):
    """
    Handles orchestrating agents that can use tools via MCP servers.

    MCP version of the OpenAI Swarm class (https://github.com/openai/swarm.)
    """

    # TODO: saqadri - streaming isn't supported yet because the underlying AugmentedLLM classes don't support it
    def __init__(self, agent: SwarmAgent, context_variables: Dict[str, str] = None):
        """
        Initialize the LLM planner with an agent, which will be used as the
        starting point for the workflow.
        """
        super().__init__(agent=agent)
        self.context_variables = defaultdict(str, context_variables or {})
        self.instruction = (
            agent.instruction(self.context_variables)
            if isinstance(agent.instruction, Callable)
            else agent.instruction
        )
        logger.debug(
            f"Swarm initialized with agent {agent.name}",
            data={
                "context_variables": self.context_variables,
                "instruction": self.instruction,
            },
        )

    async def get_tool(self, tool_name: str) -> Tool | None:
        """Get the schema for a tool by name."""
        result = await self.agent.list_tools()
        for tool in result.tools:
            if tool.name == tool_name:
                return tool

        return None

    async def pre_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest
    ) -> CallToolRequest | bool:
        if not self.agent:
            # If there are no agents, we can't do anything, so we should bail
            return False

        tool = await self.get_tool(request.params.name)
        if not tool:
            logger.warning(
                f"Warning: Tool '{request.params.name}' not found in agent '{self.agent.name}' tools. Proceeding with original request params."
            )
            return request

        # If the tool has a "context_variables" parameter, we set it to our context variables state
        if "context_variables" in tool.inputSchema:
            logger.debug(
                f"Setting context variables on tool_call '{request.params.name}'",
                data=self.context_variables,
            )
            request.params.arguments["context_variables"] = self.context_variables

        return request

    async def post_tool_call(
        self, tool_call_id: str | None, request: CallToolRequest, result: CallToolResult
    ) -> CallToolResult:
        contents = []
        for content in result.content:
            if isinstance(content, AgentResource):
                # Set the new agent as the current agent
                await self.set_agent(content.agent)
                contents.append(TextContent(type="text", text=content.resource.text))
            elif isinstance(
                content, AgentFunctionResultResource
            ):  # TODO: jerron - should this be AgentFunctionResult or AgentFunctionResultResource?
                logger.info(
                    "Updating context variables with new context variables from agent function result",
                    data=content.result.context_variables,
                )
                self.context_variables.update(content.result.context_variables)
                if content.result.agent:
                    # Set the new agent as the current agent
                    await self.set_agent(content.result.agent)

                contents.append(TextContent(type="text", text=content.resource.text))
            else:
                contents.append(content)

        result.content = contents
        return result

    async def set_agent(
        self,
        agent: SwarmAgent,
    ):
        logger.info(
            f"Switching from agent '{self.agent.name}' -> agent '{agent.name if agent else 'NULL'}'"
        )
        if self.agent:
            # Close the current agent
            await self.agent.shutdown()

        # Initialize the new agent (if it's not None)
        self.agent = agent

        if not self.agent or isinstance(self.agent, DoneAgent):
            self.instruction = None
            return

        await self.agent.initialize()
        self.instruction = (
            agent.instruction(self.context_variables)
            if callable(agent.instruction)
            else agent.instruction
        )

    def should_continue(self) -> bool:
        """
        Returns True if the workflow should continue, False otherwise.
        """
        if not self.agent or isinstance(self.agent, DoneAgent):
            return False

        return True


class DoneAgent(SwarmAgent):
    """
    A special agent that represents the end of a Swarm workflow.
    """

    def __init__(self):
        super().__init__(name="__done__", instruction="Swarm Workflow is complete.")

    async def call_tool(
        self, _name: str, _arguments: dict | None = None
    ) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text="Workflow is complete.")]
        )
