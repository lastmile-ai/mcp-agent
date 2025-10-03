import asyncio
from qdrant_client import QdrantClient
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from agent_state import get_agent_state
import streamlit as st

SAMPLE_TEXTS = [
    "Today, we're open-sourcing the Model Context Protocol (MCP), a new standard for connecting AI assistants to the systems where data lives, including content repositories, business tools, and development environments",
    "Its aim is to help frontier models produce better, more relevant responses",
    "As AI assistants gain mainstream adoption, the industry has invested heavily in model capabilities, achieving rapid advances in reasoning and quality",
    "Yet even the most sophisticated models are constrained by their isolation from data—trapped behind information silos and legacy systems",
    "Every new data source requires its own custom implementation, making truly connected systems difficult to scale",
    "MCP addresses this challenge",
    "It provides a universal, open standard for connecting AI systems with data sources, replacing fragmented integrations with a single protocol",
    "The result is a simpler, more reliable way to give AI systems access to the data they need",
    "Model Context Protocol\nThe Model Context Protocol is an open standard that enables developers to build secure, two-way connections between their data sources and AI-powered tools",
    "The architecture is straightforward: developers can either expose their data through MCP servers or build AI applications (MCP clients) that connect to these servers",
    "Today, we're introducing three major components of the Model Context Protocol for developers:\n\nThe Model Context Protocol specification and SDKs\nLocal MCP server support in the Claude Desktop apps\nAn open-source repository of MCP servers\nClaude 3",
    "5 Sonnet is adept at quickly building MCP server implementations, making it easy for organizations and individuals to rapidly connect their most important datasets with a range of AI-powered tools",
    "To help developers start exploring, we’re sharing pre-built MCP servers for popular enterprise systems like Google Drive, Slack, GitHub, Git, Postgres, and Puppeteer",
    "Early adopters like Block and Apollo have integrated MCP into their systems, while development tools companies including Zed, Replit, Codeium, and Sourcegraph are working with MCP to enhance their platforms—enabling AI agents to better retrieve relevant information to further understand the context around a coding task and produce more nuanced and functional code with fewer attempts",
    '"At Block, open source is more than a development model—it’s the foundation of our work and a commitment to creating technology that drives meaningful change and serves as a public good for all,” said Dhanji R',
    "Prasanna, Chief Technology Officer at Block",
    "“Open technologies like the Model Context Protocol are the bridges that connect AI to real-world applications, ensuring innovation is accessible, transparent, and rooted in collaboration",
    "We are excited to partner on a protocol and use it to build agentic systems, which remove the burden of the mechanical so people can focus on the creative",
    "”\n\nInstead of maintaining separate connectors for each data source, developers can now build against a standard protocol",
    "As the ecosystem matures, AI systems will maintain context as they move between different tools and datasets, replacing today's fragmented integrations with a more sustainable architecture",
    "Getting started\nDevelopers can start building and testing MCP connectors today",
    "All Claude",
    "ai plans support connecting MCP servers to the Claude Desktop app",
    "Claude for Work customers can begin testing MCP servers locally, connecting Claude to internal systems and datasets",
    "We'll soon provide developer toolkits for deploying remote production MCP servers that can serve your entire Claude for Work organization",
    "To start building:\n\nInstall pre-built MCP servers through the Claude Desktop app\nFollow our quickstart guide to build your first MCP server\nContribute to our open-source repositories of connectors and implementations\nAn open community\nWe’re committed to building MCP as a collaborative, open-source project and ecosystem, and we’re eager to hear your feedback",
    "Whether you’re an AI tool developer, an enterprise looking to leverage existing data, or an early adopter exploring the frontier, we invite you to build the future of context-aware AI together",
]


def initialize_collection():
    """Create and add data to collection."""
    client = QdrantClient("http://localhost:6333")
    client.set_model("BAAI/bge-small-en-v1.5")

    if client.collection_exists("my_collection"):
        return

    client.add(
        collection_name="my_collection",
        documents=SAMPLE_TEXTS,
    )


async def main():
    await app.initialize()

    state = await get_agent_state(
        key="agent",
        agent_class=Agent,
        llm_class=OpenAIAugmentedLLM,
        name="agent",
        instruction="""You are an intelligent assistant equipped with a 
        “find memories” tool that allows you to access information 
        about Model Context Protocol (MCP). Your primary role is to assist 
        users with queries about MCP by actively using the “find memories” 
        tool to retrieve and provide accurate responses. Always utilize the 
        “find memories” tool whenever necessary to ensure accurate information.
        """,
        server_names=["qdrant"],
    )

    tools = await state.agent.list_tools()

    st.title("💬 RAG Chatbot")
    st.caption("🚀 A Streamlit chatbot powered by mcp-agent")

    with st.expander("View Tools"):
        st.markdown(
            [f"- **{tool.name}**: {tool.description}\n\n" for tool in tools.tools]
        )

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
                response = await state.llm.generate_str(
                    message=prompt, request_params=RequestParams(use_history=True)
                )
            st.markdown(response)

        st.session_state["messages"].append({"role": "assistant", "content": response})


if __name__ == "__main__":
    initialize_collection()

    app = MCPApp(name="mcp_rag_agent")

    asyncio.run(main())
