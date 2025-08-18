from abc import ABC, abstractmethod
from typing import Callable, Dict, Generic, List, Optional, TypeVar, TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp.tools import Tool as FastTool

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)

ResultT = TypeVar("ResultT", bound=str | Agent | AugmentedLLM | Callable)


class RouterResult(BaseModel, Generic[ResultT]):
    """A class that represents the result of a Router.route request"""

    result: ResultT
    """The router returns an MCP server name, an Agent, or a function to route the input to."""

    p_score: float | None = None
    """
    The probability score (i.e. 0->1) of the routing decision. 
    This is optional and may only be provided if the router is probabilistic (e.g. a probabilistic binary classifier).
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class RouterCategory(BaseModel):
    """
    A class that represents a category of routing.
    Used to collect information the router needs to decide.
    """

    name: str
    """The name of the category"""

    description: str | None = None
    """A description of the category"""

    category: str | Agent | AugmentedLLM | Callable
    """The class to route to"""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class ServerRouterCategory(RouterCategory):
    """A class that represents a category of routing to an MCP server"""

    tools: List[FastTool] = Field(default_factory=list)


class AgentRouterCategory(RouterCategory):
    """A class that represents a category of routing to an agent"""

    servers: List[ServerRouterCategory] = Field(default_factory=list)


class Router(ABC, ContextDependent):
    """
    Routing classifies an input and directs it to one or more specialized followup tasks.
    This class helps to route an input to a specific MCP server,
    an Agent (an aggregation of MCP servers), or a function (any Callable).

    When to use this workflow:
        - This workflow allows for separation of concerns, and building more specialized prompts.

        - Routing works well for complex tasks where there are distinct categories that
        are better handled separately, and where classification can be handled accurately,
        either by an LLM or a more traditional classification model/algorithm.

    Examples where routing is useful:
        - Directing different types of customer service queries
        (general questions, refund requests, technical support)
        into different downstream processes, prompts, and tools.

        - Routing easy/common questions to smaller models like Claude 3.5 Haiku
        and hard/unusual questions to more capable models like Claude 3.5 Sonnet
        to optimize cost and speed.

    Args:
        routing_instruction: A string that tells the router how to route the input.
        mcp_servers_names: A list of server names to route the input to.
        agents: A list of agents to route the input to.
        functions: A list of functions to route the input to.
    """

    def __init__(
        self,
        server_names: List[str] | None = None,
        agents: List[Agent | AugmentedLLM] | None = None,
        functions: List[Callable] | None = None,
        routing_instruction: str | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        super().__init__(context=context, **kwargs)
        self.routing_instruction = routing_instruction
        self.server_names = server_names or []
        self.agents = agents or []
        self.functions = functions or []
        self.server_registry = self.context.server_registry

        # A dict of categories to route to, keyed by category name.
        # These are populated in the initialize method.
        self.server_categories: Dict[str, ServerRouterCategory] = {}
        self.agent_categories: Dict[str, AgentRouterCategory] = {}
        self.function_categories: Dict[str, RouterCategory] = {}
        self.categories: Dict[str, RouterCategory] = {}
        self.initialized: bool = False

        if not self.server_names and not self.agents and not self.functions:
            raise ValueError(
                "At least one of mcp_servers_names, agents, or functions must be provided."
            )

        if self.server_names and not self.server_registry:
            raise ValueError(
                "server_registry must be provided if mcp_servers_names are provided."
            )

    @abstractmethod
    async def route(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[str | Agent | AugmentedLLM | Callable]]:
        """
        Route the input request to one or more MCP servers, agents, or functions.
        If no routing decision can be made, returns an empty list.

        Args:
            request: The input to route.
            top_k: The maximum number of top routing results to return. May return fewer.
        """

    @abstractmethod
    async def route_to_server(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[str]]:
        """Route the input to one or more MCP servers."""

    @abstractmethod
    async def route_to_agent(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[Agent | AugmentedLLM]]:
        """Route the input to one or more agents."""

    @abstractmethod
    async def route_to_function(
        self, request: str, top_k: int = 1
    ) -> List[RouterResult[Callable]]:
        """
        Route the input to one or more functions.

        Args:
            input: The input to route.
        """

    async def initialize(self):
        """Initialize the router categories."""

        if self.initialized:
            return

        server_categories = [
            self.get_server_category(server_name) for server_name in self.server_names
        ]
        self.server_categories = {
            category.name: category for category in server_categories
        }

        agent_categories = [self.get_agent_category(agent) for agent in self.agents]
        self.agent_categories = {
            category.name: category for category in agent_categories
        }

        function_categories = [
            self.get_function_category(function) for function in self.functions
        ]
        self.function_categories = {
            category.name: category for category in function_categories
        }

        all_categories = server_categories + agent_categories + function_categories

        self.categories = {category.name: category for category in all_categories}
        self.initialized = True

    def get_server_category(self, server_name: str) -> ServerRouterCategory:
        server_config = self.server_registry.get_server_config(server_name)

        # TODO: saqadri - Currently we only populate the server name and description.
        # To make even more high fidelity routing decisions, we can populate the
        # tools, resources and prompts that the server has access to.
        return ServerRouterCategory(
            category=server_name,
            name=server_config.name if server_config else server_name,
            description=server_config.description,
        )

    def get_agent_category(self, agent: Agent | AugmentedLLM) -> AgentRouterCategory:
        agent_description = (
            agent.instruction({}) if callable(agent.instruction) else agent.instruction
        )

        return AgentRouterCategory(
            category=agent,
            name=agent.name,
            description=agent_description,
            servers=[
                self.get_server_category(server_name)
                for server_name in agent.server_names
            ],
        )

    def get_function_category(self, function: Callable) -> RouterCategory:
        tool = FastTool.from_function(function)

        return RouterCategory(
            category=function,
            name=tool.name,
            description=tool.description,
        )

    def format_category(
        self, category: RouterCategory, index: int | None = None
    ) -> str:
        """Format a category into a readable string."""

        index_str = f"{index}. " if index is not None else " "
        category_str = ""

        if isinstance(category, ServerRouterCategory):
            category_str = self._format_server_category(category)
        elif isinstance(category, AgentRouterCategory):
            category_str = self._format_agent_category(category)
        else:
            category_str = self._format_function_category(category)

        return f"{index_str}{category_str}"

    def _format_tools(self, tools: List[FastTool]) -> str:
        """Format a list of tools into a readable string."""
        if not tools:
            return "No tool information provided."

        tool_descriptions = []
        for tool in tools:
            desc = f"- {tool.name}: {tool.description}"
            tool_descriptions.append(desc)

        return "\n".join(tool_descriptions)

    def _format_server_category(self, category: ServerRouterCategory) -> str:
        """Format a server category into a readable string."""
        description = category.description or "No description provided"
        tools = self._format_tools(category.tools)
        return f"Server Category: {category.name}\nDescription: {description}\nTools in server:\n{tools}"

    def _format_agent_category(self, category: AgentRouterCategory) -> str:
        """Format an agent category into a readable string."""
        description = category.description or "No description provided"
        servers = "\n".join(
            [f"- {server.name} ({server.description})" for server in category.servers]
        )

        return f"Agent Category: {category.name}\nDescription: {description}\nServers in agent:\n{servers}"

    def _format_function_category(self, category: RouterCategory) -> str:
        """Format a function category into a readable string."""
        description = category.description or "No description provided"
        return f"Function Category: {category.name}\nDescription: {description}"
