# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo",
#     "mcp-agent==0.0.3",
#     "mcp==1.2.0",
#     "openai==1.60.0",
# ]
# ///

import marimo

__generated_with = "0.10.16"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # 💬 Basic agent chatbot

        **🚀 A [marimo](https://github.com/marimo-team/marimo) chatbot powered by `mcp-agent`**
        """
    )
    return


@app.cell(hide_code=True)
def _(ListToolsResult, mo, tools):
    def format_list_tools_result(list_tools_result: ListToolsResult):
        res = ""
        for tool in list_tools_result.tools:
            res += f"- **{tool.name}**: {tool.description}\n\n"
        return res

    tools_str = format_list_tools_result(tools)
    mo.accordion({"View tools": mo.md(tools_str)})
    return format_list_tools_result, tools_str


@app.cell
def _(llm, mo):
    async def model(messages, config):
        message = messages[-1]
        response = await llm.generate_str(message.content)
        return mo.md(response)

    chatbot = mo.ui.chat(
        model,
        prompts=["What are some files in my filesystem", "Get google.com"],
        show_configuration_controls=False,
    )
    chatbot
    return chatbot, model


@app.cell
async def _():
    from mcp import ListToolsResult
    import asyncio
    from mcp_agent.app import MCPApp
    from mcp_agent.agents.agent import Agent
    from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

    app = MCPApp(name="mcp_basic_agent")
    await app.initialize()
    return Agent, ListToolsResult, MCPApp, OpenAIAugmentedLLM, app, asyncio


@app.cell
async def _(Agent, OpenAIAugmentedLLM):
    finder_agent = Agent(
        name="finder",
        instruction="""You are an agent with access to the filesystem,
        as well as the ability to fetch URLs. Your job is to identify
        the closest match to a user's request, make the appropriate tool calls,
        and return the URI and CONTENTS of the closest match.""",
        server_names=["fetch", "filesystem"],
    )
    await finder_agent.initialize()
    llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
    tools = await finder_agent.list_tools()
    return finder_agent, llm, tools


@app.cell
def _():
    import marimo as mo

    return (mo,)


if __name__ == "__main__":
    app.run()
