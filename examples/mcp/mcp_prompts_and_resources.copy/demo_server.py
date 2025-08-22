import asyncio
import logging
import time
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ModelPreferences, ModelHint, SamplingMessage, TextContent
import json
import yaml

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.mcp.gen_client import gen_client
from mcp_agent.app import MCPApp
from mcp_agent.config import (
    Settings,
    LoggerSettings,
    MCPSettings,
    MCPServerSettings,
    OpenAISettings,
)
from mcp_agent.human_input.handler import console_input_callback
from mcp_agent.mcp.mcp_server_registry import ServerRegistry
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

mcp = FastMCP("Resource Demo MCP Server")

### temp: increase logging to include all details
import logging
logging.basicConfig(level=logging.DEBUG)


@mcp.resource("demo://docs/readme")
def get_readme():
    """Provide the README file content."""
    return "# Demo Resource Server\n\nThis is a sample README resource provided by the demo MCP server."


@mcp.prompt()
def echo(message: str) -> str:
    """Echo the provided message.

    This is a simple prompt that echoes back the input message.
    """
    return f"Prompt: {message}"


@mcp.resource("demo://data/friends")
def get_users():
    """Provide my friend list."""
    return (
        json.dumps(
            [
                {"id": 1, "friend": "Alice"},
            ],
        ),
    )


@mcp.prompt()
def get_haiku_prompt(topic: str) -> str:
    """Get a haiku prompt about a given topic."""
    return f"I am fascinated about {topic}. Can you generate a haiku combining {topic} + my friend name?"


secrets_file = Settings.find_secrets()
if secrets_file and secrets_file.exists():
    with open(secrets_file, "r", encoding="utf-8") as f:
        yaml_secrets = yaml.safe_load(f) or {}
        openai_secret = yaml_secrets["openai"]

settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="console", level="debug"),
    mcp=MCPSettings(
        servers={
            "haiku_server": MCPServerSettings(
                command="uv",
                args=["run", "nested_server.py"],
                description="nested server providing a haiku generator"
            )
        }
    ),
    openai=openai_secret
)

registry = ServerRegistry(settings)


@mcp.tool()
async def get_haiku(topic: str, ctx: Context) -> str:
    async with gen_client("haiku_server", registry, upstream_session=ctx.session) as haiku_client:
        result = await haiku_client.call_tool("get_haiku", {"topic": topic})
        return result.content[0].text


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
