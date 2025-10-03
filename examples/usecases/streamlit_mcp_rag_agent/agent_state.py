from dataclasses import dataclass
from typing import Optional, Type, TypeVar
import streamlit as st
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import (
    AugmentedLLM,
)

T = TypeVar("T", bound=AugmentedLLM)


@dataclass
class AgentState:
    """Container for agent and its associated LLM"""

    agent: Agent
    llm: Optional[AugmentedLLM] = None


async def get_agent_state(
    key: str,
    agent_class: Type[Agent],
    llm_class: Optional[Type[T]] = None,
    **agent_kwargs,
) -> AgentState:
    """
    Get or create agent state, reinitializing connections if retrieved from session.

    Args:
        key: Session state key
        agent_class: Agent class to instantiate
        llm_class: Optional LLM class to attach
        **agent_kwargs: Arguments for agent instantiation
    """
    if key not in st.session_state:
        # Create new agent
        agent = agent_class(
            connection_persistence=False,
            **agent_kwargs,
        )
        await agent.initialize()

        # Attach LLM if specified
        llm = None
        if llm_class:
            llm = await agent.attach_llm(llm_class)

        state: AgentState = AgentState(agent=agent, llm=llm)
        st.session_state[key] = state
    else:
        state = st.session_state[key]

    return state
