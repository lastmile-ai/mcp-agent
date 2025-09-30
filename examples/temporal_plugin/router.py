import asyncio
import os
from uuid import uuid4
from temporalio import workflow
from mcp_agent.core.context import get_current_context
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.agents.agent import Agent
from temporalio.client import Client
from mcp_agent.executor.temporal.plugin import MCPAgentPlugin
from mcp_agent.app import MCPApp
from temporalio.worker import Worker
from mcp_agent.workflows.router.router_llm import LLMRouter
from mcp_agent.workflows.router.router_llm_anthropic import AnthropicLLMRouter

app = MCPApp(name="mcp_basic_agent")


def print_to_console(message: str):
    """
    A simple function that prints a message to the console.
    """
    print(message)


def print_hello_world():
    """
    A simple function that prints "Hello, world!" to the console.
    """
    print_to_console("Hello, world!")


@workflow.defn()
class RouterWorkflow:
    @workflow.run
    async def run(self) -> str:
        context = get_current_context()
        logger = context.app.logger

        finder_agent = Agent(
            name="finder",
            instruction="""You are an agent with access to the filesystem, 
            as well as the ability to fetch URLs. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the URI and CONTENTS of the closest match.""",
            server_names=["fetch", "filesystem"],
        )

        writer_agent = Agent(
            name="writer",
            instruction="""You are an agent that can write to the filesystem.
            You are tasked with taking the user's input, addressing it, and 
            writing the result to disk in the appropriate location.""",
            server_names=["filesystem"],
        )

        reasoning_agent = Agent(
            name="reasoner",
            instruction="""You are a generalist with knowledge about a vast
            breadth of subjects. You are tasked with analyzing and reasoning over
            the user's query and providing a thoughtful response.""",
            server_names=[],
        )

        # You can use any LLM with an LLMRouter
        llm = OpenAIAugmentedLLM(name="openai_router", instruction="You are a router")
        router = LLMRouter(
            llm_factory=lambda _agent: llm,
            agents=[finder_agent, writer_agent, reasoning_agent],
            functions=[print_to_console, print_hello_world],
            context=context,
        )

        # This should route the query to finder agent, and also give an explanation of its decision
        results = await router.route_to_agent(
            request="Print the contents of mcp_agent.config.yaml verbatim", top_k=1
        )

        logger.info("Router Results:", data=results)

        # We can use the agent returned by the router
        agent = results[0].result
        async with agent:
            result = await agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            with workflow.unsafe.sandbox_unrestricted():
                config_path = str(os.path.join(os.getcwd(), "mcp_agent.config.yaml"))

            result = await agent.call_tool(
                name="read_file",
                arguments={"path": config_path},
            )
            logger.info("read_file result:", data=result.model_dump())

        # We can also use a router already configured with a particular LLM
        anthropic_router = AnthropicLLMRouter(
            server_names=["fetch", "filesystem"],
            agents=[finder_agent, writer_agent, reasoning_agent],
            functions=[print_to_console, print_hello_world],
            context=context,
        )

        # This should route the query to print_to_console function
        # Note that even though top_k is 2, it should only return print_to_console and not print_hello_world
        results = await anthropic_router.route_to_function(
            request="Print the input to console", top_k=2
        )
        logger.info("Router Results:", data=results)
        function_to_call = results[0].result
        function_to_call("Hello, world!")

        # This should route the query to fetch MCP server (inferring just by the server name alone!)
        # You can also specify a server description in mcp_agent.config.yaml to help the router make a more informed decision
        results = await anthropic_router.route_to_server(
            request="Print the first two paragraphs of https://modelcontextprotocol.io/introduction",
            top_k=1,
        )
        logger.info("Router Results:", data=results)

        # Using the 'route' function will return the top-k results across all categories the router was initialized with (servers, agents and callables)
        # top_k = 3 should likely print: 1. filesystem server, 2. finder agent and possibly 3. print_to_console function
        results = await anthropic_router.route(
            request="Print the contents of mcp_agent.config.yaml verbatim",
            top_k=3,
        )
        logger.info("Router Results:", data=results)

        return str(result)


async def main():
    async with app.run() as running_app:
        plugin = MCPAgentPlugin(running_app)

        client = await Client.connect(
            running_app.config.temporal.host,
            plugins=[plugin],
        )

        async with Worker(
            client,
            task_queue=running_app.config.temporal.task_queue,
            workflows=[RouterWorkflow],
        ):
            running_app.context.config.mcp.servers["filesystem"].args.extend(
                [os.getcwd()]
            )

            output = await client.execute_workflow(
                RouterWorkflow.run,
                id=f"basic-workflow-{uuid4()}",
                task_queue=running_app.config.temporal.task_queue,
            )
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
