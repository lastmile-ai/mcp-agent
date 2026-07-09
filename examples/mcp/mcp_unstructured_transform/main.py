import asyncio
import time

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# Settings load from mcp_agent.config.yaml. That file defines the
# `unstructured_transform` server and its browser-based OAuth auth, so no
# Unstructured API key is needed -- see the README.
app = MCPApp(name="mcp_unstructured_transform")

# A publicly reachable file the agent can parse without an upload step.
# Any https:// URL to a PDF/DOCX/PPTX/XLSX/HTML/EML/image works here.
SAMPLE_FILE_URL = "https://arxiv.org/pdf/2310.06825"  # Mistral 7B paper (PDF)


@app.tool()
async def example_usage() -> str:
    """
    Parse a document with Unstructured's hosted Transform MCP server.

    The agent connects to the `unstructured_transform` MCP server, hands it a
    public file URL, and asks for clean Markdown. Because the file is reachable
    over https, the agent can call `transform_files` directly -- no upload
    round-trip. For a local file the same server exposes `request_file_upload_url`
    (mint a signed URL -> PUT the bytes -> pass the returned u10d://file/<id> ref).
    Transforms run as jobs, so the agent also polls `check_transform_status` and
    fetches output via `get_transform_results`.
    """
    async with app.run() as agent_app:
        logger = agent_app.logger
        result = ""

        parser_agent = Agent(
            name="document_parser",
            instruction="""You are a document-parsing agent backed by the
            Unstructured Transform MCP server. Turn files into clean, structured
            output that downstream agents can act on.

            To parse a document:
              1. If the file is reachable at a public https URL, call
                 `transform_files` with that URL and the requested output format
                 (markdown, element JSON, HTML, or plain text).
              2. `transform_files` returns a job_id. Poll `check_transform_status`
                 with it until the job is complete.
              3. Fetch the finished output with `get_transform_results`.
            Return the parsed content and nothing else.""",
            server_names=["unstructured_transform"],
        )

        async with parser_agent:
            logger.info("document_parser: connected, listing tools...")
            tools_list = await parser_agent.list_tools()
            logger.info("Tools available:", data=tools_list.model_dump())

            llm = await parser_agent.attach_llm(OpenAIAugmentedLLM)

            result = await llm.generate_str(
                message=(
                    f"Transform this file to Markdown and return the result: "
                    f"{SAMPLE_FILE_URL}"
                ),
                # Cap output so a long document doesn't blow past the model's
                # completion limit.
                request_params=RequestParams(maxTokens=8192),
            )
            logger.info("Parsed document (markdown):", data={"result": result})

    return result


if __name__ == "__main__":
    start = time.time()
    asyncio.run(example_usage())
    print(f"\nTotal run time: {time.time() - start:.2f}s")
