from mcp import ListToolsResult
import streamlit as st
import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from dataclasses import dataclass
from typing import Optional, Type, TypeVar

T = TypeVar("T", bound=OpenAIAugmentedLLM)


@dataclass
class AgentState:
    """Container for agent and its associated LLM"""

    agent: Agent
    llm: Optional[OpenAIAugmentedLLM] = None


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


def format_list_tools_result(list_tools_result: ListToolsResult):
    res = ""
    for tool in list_tools_result.tools:
        res += f"- **{tool.name}**: {tool.description}\n\n"
    return res


async def main():
    await app.initialize()

    # Use the state management pattern
    state = await get_agent_state(
        key="finder_agent",
        agent_class=Agent,
        llm_class=OpenAIAugmentedLLM,
        name="finder",
        instruction="""You are an agent with access to the filesystem,
        as well as the ability to fetch URLs. Your job is to identify
        the closest match to a user's request, make the appropriate tool calls,
        and return the URI and CONTENTS of the closest match.""",
        server_names=["fetch", "filesystem"],
    )

    tools = await state.agent.list_tools()
    tools_str = format_list_tools_result(tools)

    st.title("💬 Basic Agent Chatbot")
    st.caption("🚀 A Streamlit chatbot powered by mcp-agent")

    with st.expander("View Tools"):
        st.markdown(tools_str)

    if "messages" not in st.session_state:
        st.session_state["messages"] = [
            {"role": "assistant", "content": "How can I help you?"}
        ]

    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("Type your message here..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})

        st.chat_message("user").write(prompt)

        with st.chat_message("assistant"):
            response = ""
            with st.spinner("Thinking..."):
                # Pass the conversation history to the LLM
                conversation_history = st.session_state["messages"][
                    1:
                ]  # Skip the initial greeting

                response = await state.llm.generate_str(
                    message=prompt,
                    request_params=RequestParams(
                        use_history=True,
                        history=conversation_history,  # Pass the conversation history
                    ),
                )
            st.markdown(response)

        st.session_state["messages"].append({"role": "assistant", "content": response})


if __name__ == "__main__":
    app = MCPApp(name="mcp_basic_agent")

    asyncio.run(main())
