"""
MCP Agent Sampling Handler

Handles sampling requests from MCP servers with human-in-the-loop approval workflow
and direct LLM provider integration. Falls back to upstream pass-through when present.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

from mcp.types import (
    CreateMessageRequest,
    CreateMessageRequestParams,
    CreateMessageResult,
    ErrorData,
    TextContent,
    ServerRequest,
)

from mcp.server.fastmcp.exceptions import ToolError

from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.augmented_llm import RequestParams as LLMRequestParams
from mcp_agent.workflows.llm.llm_selector import ModelSelector

logger = get_logger(__name__)

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class SamplingHandler(ContextDependent):
    """Handles MCP sampling requests with optional human approval and LLM generation."""

    def __init__(self, context: "Context"):
        super().__init__(context=context)

    async def handle_sampling(
        self, *, params: CreateMessageRequestParams
    ) -> CreateMessageResult | ErrorData:
        """Route sampling to upstream session if present, else handle locally."""
        server_session = self.context.upstream_session
        if server_session is not None:
            try:
                return await server_session.send_request(
                    request=ServerRequest(
                        CreateMessageRequest(
                            method="sampling/createMessage", params=params
                        )
                    ),
                    result_type=CreateMessageResult,
                )
            except Exception as e:
                return ErrorData(code=-32603, message=str(e))

        # No upstream session: handle locally with optional human approval + direct LLM call
        return await self._handle_sampling_locally(params)

    async def _handle_sampling_locally(
        self, params: CreateMessageRequestParams
    ) -> CreateMessageResult | ErrorData:
        try:
            approved_params, reason = await self._human_approve_request(params)
            if approved_params is None:
                return ErrorData(
                    code=-32603, message=f"Sampling request rejected by user: {reason}"
                )

            result = await self._generate_with_llm(approved_params)
            if result is None:
                return ErrorData(code=-32603, message="Failed to generate a response")

            final_result, reason = await self._human_approve_response(result)
            if final_result is None:
                return ErrorData(
                    code=-32603, message=f"Response rejected by user: {reason}"
                )
            return final_result
        except Exception as e:
            logger.error(f"Error in local sampling flow: {e}")
            return ErrorData(code=-32603, message=str(e))

    async def _human_approve_request(
        self, params: CreateMessageRequestParams
    ) -> tuple[CreateMessageRequestParams | None, str]:
        if not self.context.human_input_handler:
            return params, ""

        from mcp_agent.human_input.types import HumanInputRequest

        req = HumanInputRequest(
            prompt=(
                "MCP server requests LLM sampling. Respond 'approve' to proceed, "
                "anything else to reject (your input will be recorded as reason)."
            ),
            description="MCP Sampling Request Approval",
            request_id=f"sampling_request_{uuid4()}",
            metadata={
                "type": "sampling_request_approval",
                "original_params": params.model_dump(),
            },
        )
        resp = await self.context.human_input_handler(req)
        text = (resp.response or "").strip().lower()
        return (
            (params, "") if text == "approve" else (None, resp.response or "rejected")
        )

    async def _human_approve_response(
        self, result: CreateMessageResult
    ) -> tuple[CreateMessageResult | None, str]:
        if not self.context.human_input_handler:
            return result, ""

        from mcp_agent.human_input.types import HumanInputRequest

        req = HumanInputRequest(
            prompt=(
                "LLM has generated a response. Respond 'approve' to send, "
                "anything else to reject (your input will be recorded as reason)."
            ),
            description="MCP Sampling Response Approval",
            request_id=f"sampling_response_{uuid4()}",
            metadata={
                "type": "sampling_response_approval",
                "original_result": result.model_dump(),
            },
        )
        resp = await self.context.human_input_handler(req)
        text = (resp.response or "").strip().lower()
        return (
            (result, "") if text == "approve" else (None, resp.response or "rejected")
        )

    async def _generate_with_llm(
        self, params: CreateMessageRequestParams
    ) -> CreateMessageResult | None:
        # Require model preferences to avoid recursion/guessing
        if params.modelPreferences is None:
            raise ToolError("Model preferences must be provided for sampling requests")

        model_selector = self.context.model_selector or ModelSelector()
        model_info = model_selector.select_best_model(params.modelPreferences)

        # Lazy import to avoid circulars, and create a clean LLM instance without current context
        from mcp_agent.workflows.factory import create_llm

        # Honor the caller's systemPrompt as instruction when constructing the LLM
        llm = create_llm(
            agent_name="sampling",
            server_names=[],
            instruction=getattr(params, "systemPrompt", None),
            provider=model_info.provider,
            model=model_info.name,
            request_params=None,
            context=self.context,
        )

        # Flatten MCP SamplingMessage list to raw strings for generate_str
        messages: list[str] = []
        for m in params.messages:
            if hasattr(m.content, "text") and m.content.text:
                messages.append(m.content.text)
            elif hasattr(m.content, "data") and m.content.data:
                messages.append(str(m.content.data))
            else:
                messages.append(str(m.content))

        # Coerce optional temperature to a sane default if missing
        temperature = getattr(params, "temperature", None)
        if temperature is None:
            temperature = 0.7

        # Build request params by extending CreateMessageRequestParams so
        # everything the user provided is forwarded to the LLM
        req_params = LLMRequestParams(
            maxTokens=params.maxTokens or 2048,
            temperature=temperature,
            systemPrompt=getattr(params, "systemPrompt", None),
            includeContext=getattr(params, "includeContext", None),
            stopSequences=getattr(params, "stopSequences", None),
            metadata=getattr(params, "metadata", None),
            modelPreferences=params.modelPreferences,
            # Keep local generation simple/deterministic
            max_iterations=1,
            parallel_tool_calls=False,
            use_history=False,
            messages=None,
        )

        text = await llm.generate_str(message=messages, request_params=req_params)
        model_name = await llm.select_model(req_params) or model_info.name
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text=text),
            model=model_name,
        )
