import asyncio
import os
import time

from mcp_agent.app import MCPApp
from mcp_agent.config import (
    Settings,
    LoggerSettings,
    MCPSettings,
    MCPServerSettings,
    OpenAISettings,
    AnthropicSettings,
    MCPServerAuthSettings,
    MCPOAuthClientSettings,
    OAuthSettings,
)
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.llm_selector import ModelPreferences
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.tracing.token_counter import TokenSummary


client_id = os.environ.get("GITHUB_CLIENT_ID")
client_secret = os.environ.get("GITHUB_CLIENT_SECRET")

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="file", level="debug"),
    oauth=OAuthSettings(),
    mcp=MCPSettings(
        servers={
            "fetch": MCPServerSettings(
                command="uvx",
                args=["mcp-server-fetch"],
            ),
            "filesystem": MCPServerSettings(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem"],
            ),
            "github": MCPServerSettings(
                name="github",
                transport="streamable_http",
                url="https://api.githubcopilot.com/mcp/",
                auth=MCPServerAuthSettings(
                    oauth=MCPOAuthClientSettings(
                        enabled=True,
                        client_id=client_id,
                        client_secret=client_secret,
                        scopes=["read:org", "public_repo", "user:email"],
                        authorization_server="https://github.com/login/oauth",
                        resource="https://api.githubcopilot.com/mcp",
                        use_internal_callback=False,
                    )
                ),
            ),
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

app = MCPApp(name="oauth_basic_agent")


@app.tool()
async def example_usage() -> str:
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context
        result = ""

        logger.info("Current config:", data=context.config.model_dump())

        context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])

        finder_agent = Agent(
            name="finder",
            instruction="""You are an agent with access to the filesystem,
            as well as the ability to fetch URLs and GitHub MCP. Your job is to
            identify the closest match to a user's request, make the appropriate tool
            calls, and return useful results.""",
            server_names=["fetch", "filesystem", "github"],
        )

        async with finder_agent:
            logger.info("finder: Connected to server, calling list_tools...")
            tools_list = await finder_agent.list_tools()
            logger.info("Tools available:", data=tools_list.model_dump())

            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
            result += await llm.generate_str(
                message="Print the contents of mcp_agent.config.yaml verbatim",
            )
            logger.info(f"mcp_agent.config.yaml contents: {result}")

            llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)

            result += await llm.generate_str(
                message="Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            )
            logger.info(f"First 2 paragraphs of Model Context Protocol docs: {result}")
            result += "\n\n"

            result += await llm.generate_str(
                message="Summarize those paragraphs in a 128 character tweet",
                request_params=RequestParams(
                    modelPreferences=ModelPreferences(
                        costPriority=0.1, speedPriority=0.2, intelligencePriority=0.7
                    ),
                ),
            )

        await display_token_summary(agent_app)
    return result


async def display_token_summary(app_ctx: MCPApp, agent: Agent | None = None):
    summary: TokenSummary = await app_ctx.get_token_summary()

    print("\n" + "=" * 50)
    print("TOKEN USAGE SUMMARY")
    print("=" * 50)

    print("\nTotal Usage:")
    print(f"  Total tokens: {summary.usage.total_tokens:,}")
    print(f"  Input tokens: {summary.usage.input_tokens:,}")
    print(f"  Output tokens: {summary.usage.output_tokens:,}")
    print(f"  Total cost: ${summary.cost:.4f}")

    if summary.model_usage:
        print("\nBreakdown by Model:")
        for model_key, data in summary.model_usage.items():
            print(f"\n  {model_key}:")
            print(
                f"    Tokens: {data.usage.total_tokens:,} (input: {data.usage.input_tokens:,}, output: {data.usage.output_tokens:,})"
            )
            print(f"    Cost: ${data.cost:.4f}")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    end = time.time()
    print(f"Total run time: {end - start:.2f}s")
