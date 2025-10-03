import asyncio

import mcp.types as types
from mcp_agent.human_input.types import HumanInputRequest, HumanInputResponse
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


def _create_elicitation_message(request: HumanInputRequest) -> str:
    """Convert HumanInputRequest to elicitation message format."""
    message = request.prompt
    if request.description:
        message = f"{request.description}\n\n{message}"

    return message


def _handle_elicitation_response(
    result: types.ElicitResult, request: HumanInputRequest
) -> HumanInputResponse:
    """Convert ElicitResult back to HumanInputResponse."""
    request_id = request.request_id or ""

    # Handle different action types
    if result.action == "accept":
        if result.content and isinstance(result.content, dict):
            response_text = result.content.get("response", "")

            # Handle slash commands that might be in the response
            response_text = response_text.strip()
            if response_text.lower() in ["/decline", "/cancel"]:
                return HumanInputResponse(
                    request_id=request_id, response=response_text.lower()
                )

            return HumanInputResponse(request_id=request_id, response=response_text)
        else:
            # Fallback if content is not in expected format
            return HumanInputResponse(request_id=request_id, response="")

    elif result.action == "decline":
        return HumanInputResponse(request_id=request_id, response="decline")

    elif result.action == "cancel":
        return HumanInputResponse(request_id=request_id, response="cancel")

    else:
        # Unknown action, treat as cancel
        logger.warning(f"Unknown elicitation action: {result.action}")
        return HumanInputResponse(request_id=request_id, response="cancel")


async def elicitation_input_callback(request: HumanInputRequest) -> HumanInputResponse:
    """
    Handle human input requests using MCP elicitation.
    """

    # Try to get the context and session proxy
    try:
        from mcp_agent.core.context import get_current_context

        context = get_current_context()
        if context is None:
            raise RuntimeError("No context available for elicitation")
    except Exception:
        raise RuntimeError("No context available for elicitation")

    upstream_session = context.upstream_session

    if not upstream_session:
        raise RuntimeError("Session required for elicitation")

    try:
        message = _create_elicitation_message(request)

        logger.debug(
            "Sending elicitation request for human input",
            data={
                "request_id": request.request_id,
                "description": request.description,
                "timeout_seconds": request.timeout_seconds,
            },
        )

        # Send the elicitation request
        result = await upstream_session.elicit(
            message=message,
            requestedSchema={
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "The response or input",
                    }
                },
                "required": ["response"],
            },
            related_request_id=request.request_id,
        )

        # Convert the result back to HumanInputResponse
        response = _handle_elicitation_response(result, request)

        logger.debug(
            "Received elicitation response for human input",
            data={
                "request_id": request.request_id,
                "action": result.action,
                "response_length": len(response.response),
            },
        )

        return response

    except asyncio.TimeoutError:
        logger.warning(f"Elicitation timeout for request {request.request_id}")
        raise TimeoutError("No response received within timeout period") from None

    except Exception as e:
        logger.error(
            f"Elicitation failed for human input request {request.request_id}",
            data={"error": str(e)},
        )
        raise RuntimeError(f"Elicitation failed: {e}") from e
