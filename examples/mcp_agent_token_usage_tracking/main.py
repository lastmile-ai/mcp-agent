import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.config import (
    Settings,
    LoggerSettings,
    MCPSettings,
    MCPServerSettings,
    OpenAISettings,
    AnthropicSettings,
)
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="file", level="debug"),
    mcp=MCPSettings(
        servers={
            "fetch": MCPServerSettings(
                command="uvx",
                args=["mcp-server-fetch"],
            )
        }
    ),
    openai=OpenAISettings(
        api_key="sk-my-openai-api-key",
        default_model="gpt-4o-mini",
    ),
    anthropic=AnthropicSettings(
        api_key="sk-my-anthropic-api-key",
    ),
)

# Settings can either be specified programmatically,
# or loaded from mcp_agent.config.yaml/mcp_agent.secrets.yaml
app = MCPApp(name="mcp_basic_agent")  # settings=settings)


async def example_usage():
    async with app.run() as agent_app:
        logger = agent_app.logger

        finder_agent = Agent(
            name="finder",
            instruction="""You are an agent with the ability to fetch URLs. Your job is to identify 
            the closest match to a user's request, make the appropriate tool calls, 
            and return the URI and CONTENTS of the closest match.""",
            server_names=["fetch"],
        )

        async with finder_agent:
            logger.info("finder: Connected to server, calling list_tools...")
            result = await finder_agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            message = "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction"

            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(
                message=message,
            )

            logger.info(f"First 2 paragraphs of Model Context Protocol docs: {result}")

            openai_total_token_usage = 0
            for index, response in enumerate(llm.response_history.get()):
                logger.info(f"{index}: Token usage: {response.usage.total_tokens}")
                openai_total_token_usage += response.usage.total_tokens

            logger.info(f"OpenAI total token usage: {openai_total_token_usage}")

            # Let's switch the same agent to a different LLM
            llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)

            result = await llm.generate_str(message=message)
            logger.info("First 2 paragraphs of Model Context Protocol docs: %s", result)

            anthropic_total_token_usage = 0
            for index, response in enumerate(llm.response_history.get()):
                logger.info(
                    f"{index}: Token usage: {response.usage.input_tokens + response.usage.output_tokens}"
                )
                anthropic_total_token_usage += (
                    response.usage.input_tokens + response.usage.output_tokens
                )

            logger.info(f"Anthropic total token usage: {anthropic_total_token_usage}")

            logger.info(
                f"OpenAI uses {openai_total_token_usage} tokens, while Anthropic uses {anthropic_total_token_usage} tokens"
            )


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
