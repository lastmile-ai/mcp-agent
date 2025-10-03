import asyncio
import os
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.human_input.types import HumanInputRequest, HumanInputResponse
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


async def human_input_handler(request: HumanInputRequest) -> HumanInputResponse:
    # Simulate a single-step response
    return HumanInputResponse(
        request_id=request.request_id,
        response=f"Mocking input for request: {request.prompt}",
        metadata={"mocked": True},
    )


# Settings loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(name="agent_tracing_example", human_input_callback=human_input_handler)


async def agent_tracing():
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        logger.info("Current config:", data=context.config.model_dump())

        # Add the current directory to the filesystem server's args
        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        finder_agent = Agent(
            name="finder",
            instruction="""You are an agent with access to the filesystem, 
            as well as the ability to fetch URLs. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the URI and CONTENTS of the closest match.""",
            server_names=["fetch", "filesystem"],
            human_input_callback=human_input_handler,
        )

        async with finder_agent:
            logger.info("finder: Connected to server, calling list_tools...")
            result = await finder_agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            fetch_capabilities = await finder_agent.get_capabilities("fetch")
            logger.info("fetch capabilities:", data=fetch_capabilities.model_dump())

            filesystem_capabilities = await finder_agent.get_capabilities("filesystem")
            logger.info(
                "filesystem capabilities:", data=filesystem_capabilities.model_dump()
            )

            fetch_prompts = await finder_agent.list_prompts("fetch")
            logger.info("fetch prompts:", data=fetch_prompts.model_dump())

            filesystem_prompts = await finder_agent.list_prompts("filesystem")
            logger.info("filesystem prompts:", data=filesystem_prompts.model_dump())

            fetch_prompt = await finder_agent.get_prompt(
                "fetch_fetch", {"url": "https://modelcontextprotocol.io"}
            )
            logger.info("fetch prompt:", data=fetch_prompt.model_dump())

            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(
                message="Print the contents of mcp_agent.config.yaml verbatim",
            )
            logger.info(f"mcp_agent.config.yaml contents: {result}")

            human_input = await finder_agent.request_human_input(
                request=HumanInputRequest(
                    prompt="Please provide a URL to fetch",
                    description="This is a test human input request",
                    request_id="test_request_id",
                    workflow_id="test_workflow_id",
                    timeout_seconds=5,
                    metadata={"key": "value"},
                ),
            )

            logger.info(f"Human input: {human_input.response}")

            tool_res = await finder_agent.call_tool(
                "fetch_fetch", {"url": "https://modelcontextprotocol.io"}
            )
            logger.info(f"Tool result: {tool_res}")

            # Let's switch the same agent to a different LLM
            llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)

            result = await llm.generate_str(
                message="Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            )
            logger.info(f"First 2 paragraphs of Model Context Protocol docs: {result}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(agent_tracing())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
