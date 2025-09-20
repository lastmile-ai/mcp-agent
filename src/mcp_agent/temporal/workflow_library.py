"""
MCP Agent Temporal Workflow Library

High-level workflow functions for users of the MCP Agent Temporal plugin.
These functions provide easy-to-use interfaces for common MCP Agent operations within Temporal workflows.
"""

from typing import Any, Dict, List, Optional
from temporalio import workflow
from mcp.types import (
    CallToolRequestParams,
    Tool,
    Prompt,
    ModelPreferences,
)

from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class MCPWorkflowLibrary:
    """
    Workflow library providing high-level MCP Agent functions for use in Temporal workflows.

    This library simplifies common MCP Agent operations such as:
    - Calling MCP tools
    - Requesting human input
    - Logging messages
    - Sending notifications

    Usage in a workflow:
        @workflow.defn
        class MyWorkflow:
            @workflow.run
            async def run(self) -> str:
                mcp = MCPWorkflowLibrary()

                # Call an MCP tool
                result = await mcp.call_tool("calculator", {"operation": "add", "a": 1, "b": 2})

                # Request human input
                response = await mcp.request_human_input("Please confirm the calculation")

                # Log a message
                await mcp.log_message("info", "Calculation completed", {"result": result})

                return "Workflow completed"
    """

    @staticmethod
    async def call_tool(
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_id: Optional[str] = None,
    ) -> Any:
        """
        Call an MCP tool from within a workflow.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            server_id: Optional server ID to route the tool call

        Returns:
            The result from the tool execution
        """
        params = CallToolRequestParams(name=tool_name, arguments=arguments or {})

        # Execute as an activity
        result = await workflow.execute_activity(
            "mcp_agent.call_tool_task",
            args=[{"params": params, "server_id": server_id}],
            schedule_to_close_timeout=300,  # 5 minutes default
        )

        return result

    @staticmethod
    async def list_tools(server_id: Optional[str] = None) -> List[Tool]:
        """
        List all available MCP tools.

        Args:
            server_id: Optional server ID to query for tools

        Returns:
            List of available tools
        """
        result = await workflow.execute_activity(
            "mcp_agent.list_tools_task",
            args=[{"server_id": server_id}],
            schedule_to_close_timeout=60,
        )

        return result.get("tools", []) if isinstance(result, dict) else []

    @staticmethod
    async def get_prompt(
        prompt_name: str,
        arguments: Optional[Dict[str, str]] = None,
        server_id: Optional[str] = None,
    ) -> str:
        """
        Get an MCP prompt template.

        Args:
            prompt_name: Name of the prompt to retrieve
            arguments: Arguments to fill in the prompt template
            server_id: Optional server ID to query for the prompt

        Returns:
            The formatted prompt text
        """
        result = await workflow.execute_activity(
            "mcp_agent.get_prompt_task",
            args=[
                {
                    "prompt_name": prompt_name,
                    "arguments": arguments or {},
                    "server_id": server_id,
                }
            ],
            schedule_to_close_timeout=60,
        )

        return result.get("prompt", "") if isinstance(result, dict) else str(result)

    @staticmethod
    async def list_prompts(server_id: Optional[str] = None) -> List[Prompt]:
        """
        List all available MCP prompts.

        Args:
            server_id: Optional server ID to query for prompts

        Returns:
            List of available prompts
        """
        result = await workflow.execute_activity(
            "mcp_agent.list_prompts_task",
            args=[{"server_id": server_id}],
            schedule_to_close_timeout=60,
        )

        return result.get("prompts", []) if isinstance(result, dict) else []

    @staticmethod
    async def request_human_input(
        prompt: str, session_id: Optional[str] = None, signal_name: str = "human_input"
    ) -> Dict[str, Any]:
        """
        Request input from a human user during workflow execution.

        Args:
            prompt: The prompt/question to present to the user
            session_id: Optional session ID for tracking
            signal_name: Signal name to use for the response (default: "human_input")

        Returns:
            Dictionary containing the user's response or error information
        """
        workflow_info = workflow.info()

        result = await workflow.execute_activity(
            "mcp_request_user_input",
            args=[
                {
                    "session_id": session_id or workflow_info.workflow_id,
                    "workflow_id": workflow_info.workflow_id,
                    "execution_id": workflow_info.run_id,
                    "prompt": prompt,
                    "signal_name": signal_name,
                }
            ],
            schedule_to_close_timeout=3600,  # 1 hour for human response
        )

        return result

    @staticmethod
    async def log_message(
        level: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        namespace: str = "mcp_workflow",
    ) -> bool:
        """
        Log a message through the MCP logging system.

        Args:
            level: Log level (debug, info, warning, error, critical)
            message: The log message
            data: Optional structured data to include with the log
            namespace: Log namespace (default: "mcp_workflow")

        Returns:
            True if the log was successfully sent
        """
        workflow_info = workflow.info()

        result = await workflow.execute_activity(
            "mcp_forward_log",
            args=[
                {
                    "execution_id": workflow_info.run_id,
                    "level": level,
                    "namespace": namespace,
                    "message": message,
                    "data": data,
                }
            ],
            schedule_to_close_timeout=10,
        )

        return bool(result)

    @staticmethod
    async def notify_external(
        method: str, params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a fire-and-forget notification to an external system.

        Args:
            method: The notification method/endpoint
            params: Parameters to include with the notification

        Returns:
            True if the notification was sent (best-effort, may not confirm delivery)
        """
        workflow_info = workflow.info()

        result = await workflow.execute_activity(
            "mcp_relay_notify",
            args=[
                {
                    "execution_id": workflow_info.run_id,
                    "method": method,
                    "params": params,
                }
            ],
            schedule_to_close_timeout=5,  # Short timeout for fire-and-forget
        )

        return bool(result)

    @staticmethod
    async def request_external(
        method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a request-response call to an external system.

        Args:
            method: The request method/endpoint
            params: Parameters to include with the request

        Returns:
            Response from the external system
        """
        workflow_info = workflow.info()

        result = await workflow.execute_activity(
            "mcp_relay_request",
            args=[
                {
                    "execution_id": workflow_info.run_id,
                    "method": method,
                    "params": params,
                }
            ],
            schedule_to_close_timeout=60,
        )

        return result

    @staticmethod
    async def get_capabilities(server_id: Optional[str] = None) -> ModelPreferences:
        """
        Get the capabilities and preferences of an MCP server.

        Args:
            server_id: Optional server ID to query

        Returns:
            Model preferences and capabilities
        """
        result = await workflow.execute_activity(
            "mcp_agent.get_capabilities_task",
            args=[{"server_id": server_id}],
            schedule_to_close_timeout=30,
        )

        return result


# Export convenience functions at module level for easier access
async def call_mcp_tool(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    server_id: Optional[str] = None,
) -> Any:
    """Convenience function to call an MCP tool. See MCPWorkflowLibrary.call_tool for details."""
    return await MCPWorkflowLibrary.call_tool(tool_name, arguments, server_id)


async def request_human_input(
    prompt: str, session_id: Optional[str] = None, signal_name: str = "human_input"
) -> Dict[str, Any]:
    """Convenience function to request human input. See MCPWorkflowLibrary.request_human_input for details."""
    return await MCPWorkflowLibrary.request_human_input(prompt, session_id, signal_name)


async def log_message(
    level: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    namespace: str = "mcp_workflow",
) -> bool:
    """Convenience function to log a message. See MCPWorkflowLibrary.log_message for details."""
    return await MCPWorkflowLibrary.log_message(level, message, data, namespace)


async def notify_external(method: str, params: Optional[Dict[str, Any]] = None) -> bool:
    """Convenience function to send a notification. See MCPWorkflowLibrary.notify_external for details."""
    return await MCPWorkflowLibrary.notify_external(method, params)
