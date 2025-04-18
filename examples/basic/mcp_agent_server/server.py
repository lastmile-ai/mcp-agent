from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.workflows.parallel.parallel_llm import ParallelLLM
from mcp_agent.workflows.router.router_llm import LLMRouter

server = Server("mcp_agent")

app = MCPApp(name="mcp_server")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="call_agent",
            description="Call an agent to generate a response",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of an agent to call.",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Instructions for the agent",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to pass to an agent",
                    },
                    "server_names": {
                        "type": "array",
                        "description": "The MCP server to equip the agent with.",
                        "items": {
                            "type": "string",
                            "description": "The name of a MCP server.",
                        },
                        "uniqueItems": True,
                    },
                },
                "required": ["agent_name", "instruction", "message"],
            },
        ),
        types.Tool(
            name="list_servers",
            description="List all possible MCP servers that agent can use.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="parallel_workflow",
            description="Construct a workflows where tasks are fan-out to multiple agents and the results are aggregated by an aggregator agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_names": {
                        "type": "array",
                        "description": "The names of the agents to call.",
                        "items": {
                            "type": "string",
                            "description": "The name of an agent.",
                        },
                        "uniqueItems": True,
                    },
                    "instructions": {
                        "type": "array",
                        "description": "Instructions for the agents",
                        "items": {
                            "type": "string",
                            "description": "The instruction for each of the agents.",
                        },
                    },
                    "server_names": {
                        "type": "array",
                        "description": "A list of MCP server lists to equip each agent with. If an agent does not require MCP servers, give it an empty list.",
                        "items": {
                            "type": "array",
                            "description": "The list of the MCP servers to equip the agent with.",
                            "items": {
                                "type": "string",
                                "description": "The name of a MCP server.",
                            },
                        },
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to pass to each of the agents.",
                    },
                    "aggregator_agent": {
                        "type": "object",
                        "description": "The agent to aggregate the results.",
                        "properties": {
                            "agent_name": {
                                "type": "string",
                                "description": "The name of the agent.",
                            },
                            "instruction": {
                                "type": "string",
                                "description": "The instruction for the agent.",
                            },
                            "server_names": {
                                "type": "array",
                                "description": "The MCP server to equip the agent with.",
                                "items": {
                                    "type": "string",
                                    "description": "The name of a MCP server.",
                                },
                                "uniqueItems": True,
                            },
                        },
                        "required": ["agent_name", "instruction", "server_names"],
                    },
                    "required": [
                        "agent_names",
                        "instructions",
                        "message",
                        "aggregator_agent",
                    ],
                },
            },
        ),
        types.Tool(
            name="router_workflow",
            description="Given an input, find the most relevant agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to the router.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "The number of agents to route the message to based on relevance.",
                        "minimum": 1,
                    },
                    "agent_names": {
                        "type": "array",
                        "description": "The names of the agents to call.",
                        "items": {
                            "type": "string",
                            "description": "The name of an agent.",
                        },
                        "uniqueItems": True,
                    },
                    "instructions": {
                        "type": "array",
                        "description": "Instructions for the agents",
                        "items": {
                            "type": "string",
                            "description": "The instruction for each of the agents.",
                        },
                    },
                    "server_names": {
                        "type": "array",
                        "description": "A list of MCP server lists to equip each agent with. If an agent does not require MCP servers, give it an empty list.",
                        "items": {
                            "type": "array",
                            "description": "The list of the MCP servers to equip the agent with.",
                            "items": {
                                "type": "string",
                                "description": "The name of a MCP server.",
                            },
                        },
                    },
                },
                "required": [
                    "message",
                    "top_k",
                    "agent_names",
                    "instructions",
                ],
            },
        ),
        types.Tool(
            name="orchestrator_workflow",
            description="Construct a workflow where a higher llm breaks tasks into steps, assigns them to agents, and merges results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to the orchestrator.",
                    },
                    "agent_names": {
                        "type": "array",
                        "description": "The names of the agents that can be called.",
                        "items": {
                            "type": "string",
                            "description": "The name of an agent.",
                        },
                    },
                    "instructions": {
                        "type": "array",
                        "description": "Instructions for the agents",
                        "items": {
                            "type": "string",
                            "description": "The instruction for each of the agents.",
                        },
                    },
                    "server_names": {
                        "type": "array",
                        "description": "A list of MCP server lists to equip each agent with. If an agent does not require MCP servers, give it an empty list.",
                        "items": {
                            "type": "array",
                            "description": "The list of the MCP servers to equip the agent with.",
                            "items": {
                                "type": "string",
                                "description": "The name of a MCP server.",
                            },
                        },
                    },
                },
                "required": ["message", "agent_names", "instructions"],
            },
        ),
    ]


async def run_parallel_workflow(arguments: dict) -> list[types.TextContent]:
    agent_names = arguments.get("agent_names")
    instructions = arguments.get("instructions")
    message = arguments.get("message")
    server_names = arguments.get("server_names")
    aggregator_agent = arguments.get("aggregator_agent")

    if not isinstance(agent_names, list):
        raise ValueError("agent_names must be a list")
    elif not all(isinstance(name, str) for name in agent_names):
        raise ValueError("Each agent_name must be a string")
    elif not isinstance(instructions, list):
        raise ValueError("instructions must be a list")
    elif not all(isinstance(instruction, str) for instruction in instructions):
        raise ValueError("Each instruction must be a string")
    elif not isinstance(message, str):
        raise ValueError("message must be a string")
    elif len(agent_names) != len(instructions):
        raise ValueError("agent_names and instructions must have the same length")
    elif server_names is not None and (len(agent_names) != len(server_names)):
        raise ValueError("agent_names and server_names must have the same length")

    server_names = server_names or [[] for _ in agent_names]
    fan_out_agents = [
        Agent(name=agent_name, instruction=instruction, server_names=servers)
        for agent_name, instruction, servers in zip(
            agent_names, instructions, server_names
        )
    ]
    fan_in_agent = Agent(
        aggregator_agent["agent_name"], aggregator_agent["instruction"]
    )

    parallel = ParallelLLM(
        fan_in_agent=fan_in_agent,
        fan_out_agents=fan_out_agents,
        llm_factory=OpenAIAugmentedLLM,
    )

    result = await parallel.generate_str(message)
    return [types.TextContent(type="text", text=result)]


def run_list_servers() -> list[types.TextContent]:
    context = app.context
    servers = list(context.config.mcp.servers.keys())
    return [types.TextContent(type="text", text="\n".join(servers))]


async def run_call_agent(arguments: dict) -> list[types.TextContent]:
    agent_name = arguments.get("agent_name")
    instruction = arguments.get("instruction")
    message = arguments.get("message")
    server_names = arguments.get("server_names")

    if not agent_name:
        raise ValueError("Missing agent_name parameter")
    elif not instruction:
        raise ValueError("Missing instruction parameter")
    elif not message:
        raise ValueError("Missing message parameter")

    agent = Agent(name=agent_name, instruction=instruction, server_names=server_names)

    await agent.initialize()

    llm = await agent.attach_llm(OpenAIAugmentedLLM)

    result = await llm.generate_str(
        message=message,
    )

    return [types.TextContent(type="text", text=result)]


async def run_router_workflow(arguments: dict) -> list[types.TextContent]:
    agent_names = arguments.get("agent_names")
    instructions = arguments.get("instructions")
    message = arguments.get("message")
    top_k = arguments.get("top_k")
    server_names = arguments.get("server_names")

    if not isinstance(agent_names, list):
        raise ValueError("agent_names must be a list")
    elif not isinstance(instructions, list):
        raise ValueError("instructions must be a list")
    elif not isinstance(message, str):
        raise ValueError("message must be a string")
    elif not isinstance(top_k, int):
        raise ValueError("top_k must be an integer")

    server_names = server_names or [[] for _ in agent_names]
    agents = [
        Agent(name=agent_name, instruction=instruction, server_names=servers)
        for agent_name, instruction, servers in zip(
            agent_names, instructions, server_names
        )
    ]

    router = LLMRouter(llm=OpenAIAugmentedLLM, agents=agents)
    responses = await router.route_to_agent(message, top_k)

    result = "\n\n---\n\n".join(
        [
            f"Agent: {response.result.name}\nConfidence: {response.confidence}\nReasoning: {response.reasoning}"
            for response in responses
        ]
    )
    return [types.TextContent(type="text", text=result)]


async def run_orchestrator_workflow(arguments: dict) -> list[types.TextContent]:
    agent_names = arguments.get("agent_names")
    instructions = arguments.get("instructions")
    message = arguments.get("message")
    server_names = arguments.get("server_names")

    if not isinstance(agent_names, list):
        raise ValueError("agent_names must be a list")
    elif not isinstance(instructions, list):
        raise ValueError("instructions must be a list")
    elif not isinstance(message, str):
        raise ValueError("message must be a string")

    server_names = server_names or [[] for _ in agent_names]
    agents = [
        Agent(name=agent_name, instruction=instruction, server_names=servers)
        for agent_name, instruction, servers in zip(
            agent_names, instructions, server_names
        )
    ]

    orchestrator = Orchestrator(llm_factory=OpenAIAugmentedLLM, available_agents=agents)
    result = await orchestrator.generate_str(message)

    return [types.TextContent(type="text", text=result)]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    if arguments is None:
        raise ValueError("Missing arguments")

    try:
        await app.initialize()
        if name == "call_agent":
            return await run_call_agent(arguments)
        elif name == "list_servers":
            return run_list_servers()
        elif name == "parallel_workflow":
            return await run_parallel_workflow(arguments)
        elif name == "router_workflow":
            return await run_router_workflow(arguments)
        elif name == "orchestrator_workflow":
            return await run_orchestrator_workflow(arguments)
        else:
            ValueError(f"Unknown tool: {name}")

    except Exception as e:
        raise ValueError(f"Error: {e}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp_agent",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
