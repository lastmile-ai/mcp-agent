from typing import Callable, Any

from mcp_agent.agents.types import LLM

from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ListToolsResult,
    ListResourcesResult,
    PromptMessage,
)


class AuthorizationEngine:
    """
    Base class for authorization engines. Provides default noop implementation
    for APIs that support authorization. This can be extended to cover APIs from
    different parts of the framework such as from the Agent.
    """

    async def list_tools_authorize(
        self,
        agent,
        fn: Callable[..., ListToolsResult],
        *args,
        **kwargs,
    ) -> ListToolsResult:
        """Authorizer function for list_tools Agent API."""

        return await fn(agent, *args, **kwargs)

    async def attach_llm_authorize(
        self,
        agent,
        fn: Callable[..., LLM],
        *args,
        **kwargs,
    ) -> LLM:
        """Authorizer function for attach_llm Agent API."""

        return await fn(agent, *args, **kwargs)

    async def list_resources_authorize(
        self,
        agent,
        fn: Callable[..., ListResourcesResult],
        *args,
        **kwargs,
    ) -> ListResourcesResult:
        """Authorizer function for list_resources Agent API."""

        return await fn(agent, *args, **kwargs)

    async def read_resource_authorize(
        self,
        agent,
        fn: Callable[..., Any],
        *args,
        **kwargs,
    ) -> Any:
        """Authorizer function for read_resource Agent API."""

        return await fn(agent, *args, **kwargs)

    async def create_prompt_authorize(
        self,
        agent,
        fn: Callable[..., list[PromptMessage]],
        *args,
        **kwargs,
    ) -> list[PromptMessage]:
        """Authorizer function for create_prompt Agent API."""

        return await fn(agent, *args, **kwargs)

    async def list_prompts_authorize(
        self,
        agent,
        fn: Callable[..., ListPromptsResult],
        *args,
        **kwargs,
    ) -> ListPromptsResult:
        """Authorizer function for list_prompts Agent API."""

        return await fn(agent, *args, **kwargs)

    async def get_prompt_authorize(
        self,
        agent,
        fn: Callable[..., GetPromptResult],
        *args,
        **kwargs,
    ) -> GetPromptResult:
        """Authorizer function for get_prompt Agent API."""

        return await fn(agent, *args, **kwargs)

    async def call_tool_authorize(
        self,
        agent,
        fn: Callable[..., CallToolResult],
        *args,
        **kwargs,
    ) -> CallToolResult:
        """Authorizer function for call_tool Agent API."""

        return await fn(agent, *args, **kwargs)
