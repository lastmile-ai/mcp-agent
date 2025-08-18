import asyncio
import json
import time
from mcp.types import CallToolResult
from mcp_agent.app import MCPApp
from mcp_agent.config import MCPServerSettings
from mcp_agent.executor.workflow import WorkflowExecution
from mcp_agent.mcp.gen_client import gen_client


async def main():
    # Create MCPApp to get the server registry
    app = MCPApp(name="workflow_mcp_client")
    async with app.run() as client_app:
        logger = client_app.logger
        context = client_app.context

        # Connect to the workflow server
        logger.info("Connecting to workflow server...")

        # Override the server configuration to point to our local script
        context.server_registry.registry["basic_agent_server"] = MCPServerSettings(
            name="basic_agent_server",
            description="Local workflow server running the basic agent example",
            transport="sse",
            url="http://0.0.0.0:8000/sse",
        )

        # Connect to the workflow server
        async with gen_client("basic_agent_server", context.server_registry) as server:
            # Call the BasicAgentWorkflow
            run_result = await server.call_tool(
                "workflows-BasicAgentWorkflow-run",
                arguments={
                    "run_parameters": {
                        "input": "Print the first 2 paragraphs of https://modelcontextprotocol.io/introduction"
                    }
                },
            )

            execution = WorkflowExecution(**json.loads(run_result.content[0].text))
            run_id = execution.run_id
            logger.info(
                f"Started BasicAgentWorkflow-run. workflow ID={execution.workflow_id}, run ID={run_id}"
            )

            # Wait for the workflow to complete
            while True:
                get_status_result = await server.call_tool(
                    "workflows-BasicAgentWorkflow-get_status",
                    arguments={"run_id": run_id},
                )

                workflow_status = _tool_result_to_json(get_status_result)
                if workflow_status is None:
                    logger.error(
                        f"Failed to parse workflow status response: {get_status_result}"
                    )
                    break

                logger.info(
                    f"Workflow run {run_id} status:",
                    data=workflow_status,
                )

                if not workflow_status.get("status"):
                    logger.error(
                        f"Workflow run {run_id} status is empty. get_status_result:",
                        data=get_status_result,
                    )
                    break

                if workflow_status.get("status") == "completed":
                    logger.info(
                        f"Workflow run {run_id} completed successfully! Result:",
                        data=workflow_status.get("result"),
                    )

                    break
                elif workflow_status.get("status") == "error":
                    logger.error(
                        f"Workflow run {run_id} failed with error:",
                        data=workflow_status,
                    )
                    break
                elif workflow_status.get("status") == "running":
                    logger.info(
                        f"Workflow run {run_id} is still running...",
                    )
                elif workflow_status.get("status") == "cancelled":
                    logger.error(
                        f"Workflow run {run_id} was cancelled.",
                        data=workflow_status,
                    )
                    break
                else:
                    logger.error(
                        f"Unknown workflow status: {workflow_status.get('status')}",
                        data=workflow_status,
                    )
                    break

                await asyncio.sleep(5)

                # TODO: UNCOMMENT ME to try out cancellation:
                # await server.call_tool(
                #     "workflows-cancel",
                #     arguments={"workflow_id": "BasicAgentWorkflow", "run_id": run_id},
                # )

            print(run_result)


def _tool_result_to_json(tool_result: CallToolResult):
    if tool_result.content and len(tool_result.content) > 0:
        text = tool_result.content[0].text
        try:
            # Try to parse the response as JSON if it's a string
            import json

            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, just use the text
            return None


if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")
