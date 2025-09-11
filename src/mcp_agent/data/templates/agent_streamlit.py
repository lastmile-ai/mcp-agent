#!/usr/bin/env python3
"""Streamlit-based MCP-Agent interface."""

import streamlit as st
import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.workflows.factory import create_llm

# Page configuration
st.set_page_config(page_title="MCP Agent Chat", page_icon="🤖", layout="wide")


# Create the MCP application
@st.cache_resource
def get_app():
    app = MCPApp("Streamlit Agent")

    # Define an agent
    agent = AgentSpec(
        name="assistant",
        instruction="You are a helpful AI assistant with access to various tools.",
        server_names=["filesystem", "fetch"],
    )

    app.register_agent("assistant", agent)
    return app


# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# UI Layout
st.title("🤖 MCP Agent Chat")
st.markdown("Chat with an AI agent that has access to MCP servers.")

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")

    model_provider = st.selectbox(
        "Provider", ["anthropic", "openai", "google"], index=0
    )

    model_name = st.text_input(
        "Model", value="haiku" if model_provider == "anthropic" else "gpt-4o"
    )

    st.divider()

    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Chat interface
chat_container = st.container()

# Display chat history
with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Type your message here..."):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            app = get_app()

            async def generate_response():
                async with app.run():
                    llm = create_llm(
                        agent_name="assistant",
                        server_names=["filesystem", "fetch"],
                        provider=model_provider,
                        model=f"{model_provider}.{model_name}",
                        context=app.context,
                    )
                    return await llm.generate_str(prompt)

            # Run async function
            response = asyncio.run(generate_response())
            st.markdown(response)

    # Add assistant message to history
    st.session_state.messages.append({"role": "assistant", "content": response})
