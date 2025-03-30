"""
Chain workflow implementation using the clean BaseAgent adapter pattern.

This provides an implementation that delegates operations to a sequence of
other agents, chaining their outputs together.
"""

from typing import Any, List, Optional, Type, Union

from mcp.types import TextContent

from mcp_agent.agents.agent import Agent, AgentConfig
from mcp_agent.core.base_agent import BaseAgent
from mcp_agent.core.prompt import Prompt
from mcp_agent.core.request_params import RequestParams
from mcp_agent.mcp.interfaces import ModelT
from mcp_agent.mcp.prompt_message_multipart import PromptMessageMultipart


class ChainAgent(BaseAgent):
    """
    A chain agent that processes requests through a series of specialized agents in sequence.
    Passes the output of each agent to the next agent in the chain.
    """

    def __init__(
        self,
        config: Union[AgentConfig, str],
        agents: List[Agent],
        cumulative: bool = False,
        context: Optional[Any] = None,
        **kwargs,
    ) -> None:
        """
        Initialize a ChainAgent.

        Args:
            config: Agent configuration or name
            agents: List of agents to chain together in sequence
            cumulative: Whether each agent sees all previous responses
            context: Optional context object
            **kwargs: Additional keyword arguments to pass to BaseAgent
        """
        super().__init__(config, context=context, **kwargs)
        self.agents = agents
        self.cumulative = cumulative

    async def generate_x(
        self,
        multipart_messages: List[PromptMessageMultipart],
        request_params: Optional[RequestParams] = None,
    ) -> PromptMessageMultipart:
        """
        Chain the request through multiple agents in sequence.

        Args:
            multipart_messages: Initial messages to send to the first agent
            request_params: Optional request parameters

        Returns:
            The response from the final agent in the chain
        """
        if not self.agents:
            # If no agents in the chain, return an empty response
            return PromptMessageMultipart(
                role="assistant",
                content=[TextContent(type="text", text="No agents available in the chain.")],
            )

        # Get the original user message (last message in the list)
        user_message = multipart_messages[-1] if multipart_messages else None

        # If no user message, return an error
        if not user_message:
            return PromptMessageMultipart(
                role="assistant",
                content=[TextContent(type="text", text="No input message provided.")],
            )

        # Initialize messages with the input
        current_messages = multipart_messages

        # Track all responses in the chain
        all_responses: List[PromptMessageMultipart] = []
        
        # For cumulative mode with proper XML tagging
        if self.cumulative:
            # Initialize list for storing formatted results
            final_results: List[str] = []
            
            # Add the original request with XML tag
            request_text = f"<fastagent:request>{user_message.all_text()}</fastagent:request>"
            final_results.append(request_text)
            
        # Process through each agent in sequence
        for i, agent in enumerate(self.agents):
            # Determine what to send to this agent
            if self.cumulative and all_responses:
                # In cumulative mode, include the original message and all previous responses
                chain_messages = multipart_messages.copy()
                chain_messages.extend(all_responses)
                current_response = await agent.generate_x(chain_messages, request_params)
            else:
                # In sequential mode, just pass the current messages to the next agent
                current_response = await agent.generate_x(current_messages, request_params)

            # Store the response
            all_responses.append(current_response)
            
            # In cumulative mode, format with XML tags
            if self.cumulative:
                agent_name = getattr(agent, "name", f"agent{i}")
                response_text = current_response.all_text()
                attributed_response = f"<fastagent:response agent='{agent_name}'>{response_text}</fastagent:response>"
                final_results.append(attributed_response)

            # Prepare for the next agent (in sequential mode)
            if i < len(self.agents) - 1:
                # In sequential mode, we only pass the output of the previous agent
                # to the next agent in the chain, without the original message
                current_messages = [current_response]

        # Return the appropriate response format
        if self.cumulative:
            # For cumulative mode, return the properly formatted output with XML tags
            response_text = "\n\n".join(final_results)
            return PromptMessageMultipart(
                role="assistant",
                content=[TextContent(type="text", text=response_text)],
            )
        else:
            # For non-cumulative mode, just return the final agent's response directly
            return all_responses[-1] if all_responses else PromptMessageMultipart(
                role="assistant",
                content=[TextContent(type="text", text="")],
            )

    async def structured(
        self,
        prompt: List[PromptMessageMultipart],
        model: Type[ModelT],
        request_params: Optional[RequestParams] = None,
    ) -> Optional[ModelT]:
        """
        Chain the request through multiple agents and parse the final response.

        Args:
            prompt: List of messages to send through the chain
            model: Pydantic model to parse the final response into
            request_params: Optional request parameters

        Returns:
            The parsed response from the final agent, or None if parsing fails
        """
        # Generate response through the chain
        response = await self.generate_x(prompt, request_params)

        # Let the last agent in the chain try to parse the response
        if self.agents:
            last_agent = self.agents[-1]
            try:
                return await last_agent.structured([response], model, request_params)
            except Exception as e:
                self.logger.warning(f"Failed to parse response from chain: {str(e)}")
                return None
        return None

    async def initialize(self) -> None:
        """
        Initialize the chain agent and all agents in the chain.
        """
        await super().initialize()

        # Initialize all agents in the chain if not already initialized
        for agent in self.agents:
            if not getattr(agent, "initialized", False):
                await agent.initialize()

    async def shutdown(self) -> None:
        """
        Shutdown the chain agent and all agents in the chain.
        """
        await super().shutdown()

        # Shutdown all agents in the chain
        for agent in self.agents:
            try:
                await agent.shutdown()
            except Exception as e:
                self.logger.warning(f"Error shutting down agent in chain: {str(e)}")
