import asyncio
import inspect
import os
import time

from mcp_agent.app import MCPApp
from mcp_agent.config import get_settings, OAuthTokenStoreSettings, OAuthSettings
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.tracing.token_counter import TokenSummary


def _load_settings():
    signature = inspect.signature(get_settings)
    if "set_global" in signature.parameters:
        return get_settings(set_global=False)
    return get_settings()


settings = _load_settings()

redis_url = os.environ.get("OAUTH_REDIS_URL")
if redis_url:
    settings.oauth = settings.oauth or OAuthSettings()
    settings.oauth.token_store = OAuthTokenStoreSettings(
        backend="redis",
        redis_url=redis_url,
    )
elif not getattr(settings.oauth, "token_store", None):
    settings.oauth = settings.oauth or OAuthSettings()
    settings.oauth.token_store = OAuthTokenStoreSettings()

github_settings = (
    settings.mcp.servers.get("github")
    if settings.mcp and settings.mcp.servers
    else None
)
github_oauth = (
    github_settings.auth.oauth
    if github_settings and github_settings.auth and github_settings.auth.oauth
    else None
)

if not github_oauth or not github_oauth.client_id or not github_oauth.client_secret:
    raise SystemExit(
        "GitHub OAuth client_id/client_secret must be provided via mcp_agent.config.yaml or mcp_agent.secrets.yaml."
    )

app = MCPApp(
    name="oauth_basic_agent", settings=settings, session_id="oauth-basic-agent"
)


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

            # GitHub MCP server use
            github_repos = await llm.generate_str(
                message="Use the GitHub MCP server to find the top 3 public repositories for the GitHub organization lastmile-ai and list their names.",
            )
            logger.info(
                f"Top 3 public repositories for the GitHub organization lastmile-ai: {github_repos}"
            )

            result += f"\n\nTop 3 public repositories for the GitHub organization lastmile-ai: {github_repos}"

            # Filesystem MCP server use
            config_contents = await llm.generate_str(
                message="Print the contents of mcp_agent.config.yaml verbatim",
            )
            logger.info(f"mcp_agent.config.yaml contents: {config_contents}")
            result += f"\n\nContents of mcp_agent.config.yaml: {config_contents}"

            # Switch to Anthropic LLM
            llm = await finder_agent.attach_llm(AnthropicAugmentedLLM)

            # fetch MCP server use
            mcp_introduction = await llm.generate_str(
                message="Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction",
            )
            logger.info(
                f"First 2 paragraphs of Model Context Protocol docs: {mcp_introduction}"
            )
            result += f"\n\nFirst 2 paragraphs of Model Context Protocol docs: {mcp_introduction}"

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
