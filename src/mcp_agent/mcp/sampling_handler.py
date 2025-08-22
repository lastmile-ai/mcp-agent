"""
MCP Agent Sampling Handler

Handles sampling requests from MCP servers with human-in-the-loop approval workflow
and direct LLM provider integration.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

from mcp.types import (
    CreateMessageRequestParams,
    CreateMessageResult,
    ErrorData,
    TextContent,
    ImageContent,
    SamplingMessage,
)

from mcp_agent.core.context_dependent import ContextDependent
from mcp_agent.logging.logger import get_logger
from mcp_agent.workflows.llm.augmented_llm import (
    AugmentedLLM,
    RequestParams as LLMRequestParams,
)

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

logger = get_logger(__name__)


class SamplingHandler(ContextDependent):
    """Handles MCP sampling requests with human approval workflow and LLM generation"""

    def __init__(self, context: "Context"):
        super().__init__(context=context)

    async def handle_sampling_with_human_approval(
        self, params: CreateMessageRequestParams
    ) -> CreateMessageResult | ErrorData:
        """Handle sampling with human-in-the-loop approval workflow"""
        try:
            # Stage 1: Human approval/modification of the request
            approved_params, rejection_reason = await self._request_human_approval_for_sampling_request(
                params
            )
            if approved_params is None:
                logger.info(f"Sampling request rejected by user: {rejection_reason}")
                return ErrorData(
                    code=-32603, message=f"Sampling request rejected by user: {rejection_reason}"
                )

            # Stage 2: Generate response using available LLM providers
            llm_result = await self._generate_with_active_llm_provider(approved_params)
            if llm_result is None:
                return ErrorData(code=-32603, message="Failed to generate a response")

            # Stage 3: Human approval/modification of the response
            final_result, rejection_reason = await self._request_human_approval_for_sampling_response(
                llm_result
            )
            if final_result is None:
                logger.info(f"Sampling response rejected by user: {rejection_reason}")
                return ErrorData(code=-32603, message=f"Response rejected by user: {rejection_reason}")

            return final_result

        except Exception as e:
            logger.error(f"Error in sampling with human approval: {e}")
            return ErrorData(code=-32603, message=str(e))

    async def _request_human_approval_for_sampling_request(
        self, params: CreateMessageRequestParams
    ) -> tuple[CreateMessageRequestParams | None, str]:
        """Present sampling request to user for approval/modification"""
        try:
            if not self.context.human_input_handler:
                logger.warning(
                    "No human input handler available, auto-approving request"
                )
                return params, ""

            request_summary = self._format_sampling_request_for_human(params)

            from mcp_agent.human_input.types import HumanInputRequest

            request_id = f"sampling_request_{uuid4()}"

            request = HumanInputRequest(
                prompt=f"""MCP server is requesting LLM completion. Please review and approve/reject:

{request_summary}

Respond with:
- 'approve' to proceed with the request as-is
- Anything else to reject (your input will be used as the rejection reason)""",
                description="MCP Sampling Request Approval",
                request_id=request_id,
                metadata={
                    "type": "sampling_request_approval",
                    "original_params": params.model_dump(),
                },
            )

            response = await self.context.human_input_handler(request)
            return self._parse_human_modified_params(response.response, params)

        except Exception as e:
            logger.error(f"Error requesting human approval for sampling request: {e}")
            return params, ""  # Fallback to original params

    async def _request_human_approval_for_sampling_response(
        self, result: CreateMessageResult
    ) -> tuple[CreateMessageResult | None, str]:
        """Present LLM response to user for approval/modification"""
        try:
            if not self.context.human_input_handler:
                logger.warning(
                    "No human input handler available, auto-approving response"
                )
                return result, ""

            response_summary = self._format_sampling_response_for_human(result)

            from mcp_agent.human_input.types import HumanInputRequest

            request_id = f"sampling_response_{uuid4()}"

            request = HumanInputRequest(
                prompt=f"""LLM has generated a response. Please review and approve/reject:

{response_summary}

Respond with:
- 'approve' to send the response as-is
- Anything else to reject (your input will be used as the rejection reason)""",
                description="MCP Sampling Response Approval",
                request_id=request_id,
                metadata={
                    "type": "sampling_response_approval",
                    "original_result": result.model_dump(),
                },
            )

            response = await self.context.human_input_handler(request)
            return self._parse_human_modified_result(response.response, result)

        except Exception as e:
            logger.error(f"Error requesting human approval for sampling response: {e}")
            return result, ""  # Fallback to original result

    async def _generate_with_active_llm_provider(
        self, params: CreateMessageRequestParams
    ) -> CreateMessageResult | None:
        """Generate using active LLM's provider with improved error handling"""
        try:
            active_llm = self.context.active_llm
            if not active_llm:
                logger.error("No active LLM provider available")
                return None

            provider_class = active_llm.__class__
            if not provider_class:
                logger.error(
                    f"No provider class found for active LLM provider: {getattr(active_llm, 'provider', 'unknown')}"
                )
                return None

            return await self._call_provider_directly(provider_class, params)

        except AttributeError as e:
            logger.error(f"Failed to access active LLM provider: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in LLM provider generation: {e}")
            return None

    async def _call_provider_directly(
        self,
        provider_class: type[AugmentedLLM],
        params: CreateMessageRequestParams,
    ) -> CreateMessageResult | None:
        """Call provider API directly without tool execution to avoid recursion"""
        provider_name = getattr(provider_class, "__name__", "Unknown")

        try:
            llm = self._create_provider_instance(provider_class)
            if not llm:
                return None

            messages = self._extract_message_content(params.messages)
            request_params = self._build_llm_request_params(params)

            result = await llm.generate_str(
                message=messages, request_params=request_params
            )

            logger.info(f"Successfully generated response with {provider_name}")
            final_request_params = llm.get_request_params(
                self._build_llm_request_params(params)
            )
            model_name = await llm.select_model(final_request_params)
            return CreateMessageResult(
                role="assistant",
                content=TextContent(type="text", text=result),
                model=model_name or "unknown",
            )

        except ImportError as e:
            logger.error(f"Provider {provider_name} dependencies not available: {e}")
            return None
        except AttributeError as e:
            logger.error(f"Provider {provider_name} missing required methods: {e}")
            return None
        except ValueError as e:
            logger.error(f"Invalid parameters for provider {provider_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling provider {provider_name}: {e}")
            return None

    def _create_provider_instance(
        self, provider_class: type[AugmentedLLM]
    ) -> AugmentedLLM | None:
        """Create a minimal LLM instance for direct calls"""
        try:
            return provider_class(context=self.context)
        except Exception as e:
            logger.error(f"Failed to create provider instance: {e}")
            return None

    def _extract_message_content(self, messages: list[SamplingMessage]) -> list[str]:
        """Extract text content from MCP messages"""
        extracted = []
        for msg in messages:
            content = self._get_message_text(msg.content)
            extracted.append(content)
        return extracted

    def _get_message_text(self, content: TextContent | ImageContent) -> str:
        """Extract text from message content with fallback handling"""
        if hasattr(content, "text") and content.text:
            return content.text
        elif hasattr(content, "data") and content.data:
            return str(content.data)
        else:
            return str(content)

    def _build_llm_request_params(
        self, params: CreateMessageRequestParams
    ) -> LLMRequestParams:
        """Build LLM request parameters with safe defaults"""
        return LLMRequestParams(
            maxTokens=params.maxTokens or 2048,
            temperature=getattr(params, "temperature", 0.7),
            max_iterations=1,
            parallel_tool_calls=False,
            use_history=False,
            messages=None,
            modelPreferences = params.modelPreferences,
        )

    def _format_sampling_request_for_human(
        self, params: CreateMessageRequestParams
    ) -> str:
        """Format sampling request for human review"""
        messages_text = ""
        for i, msg in enumerate(params.messages):
            content = (
                msg.content.text if hasattr(msg.content, "text") else str(msg.content)
            )
            messages_text += f"  Message {i+1} ({msg.role}): {content[:200]}{'...' if len(content) > 200 else ''}\n"

        system_prompt_display = (
            "None"
            if params.systemPrompt is None
            else (
                f"{params.systemPrompt[:100]}{'...' if len(params.systemPrompt) > 100 else ''}"
            )
        )

        stop_sequences_display = (
            "None" if params.stopSequences is None else str(params.stopSequences)
        )

        model_preferences_display = "None"
        if params.modelPreferences is not None:
            prefs = []
            if params.modelPreferences.hints:
                hints = [
                    hint.name
                    for hint in params.modelPreferences.hints
                    if hint.name is not None
                ]
                prefs.append(f"hints: {hints}")
            if params.modelPreferences.costPriority is not None:
                prefs.append(f"cost: {params.modelPreferences.costPriority}")
            if params.modelPreferences.speedPriority is not None:
                prefs.append(f"speed: {params.modelPreferences.speedPriority}")
            if params.modelPreferences.intelligencePriority is not None:
                prefs.append(
                    f"intelligence: {params.modelPreferences.intelligencePriority}"
                )
            model_preferences_display = ", ".join(prefs) if prefs else "None"

        return f"""REQUEST DETAILS:
- Max Tokens: {params.maxTokens}
- System Prompt: {system_prompt_display}
- Temperature: {params.temperature if params.temperature is not None else 0.7}
- Stop Sequences: {stop_sequences_display}
- Model Preferences: {model_preferences_display}

MESSAGES:
{messages_text}"""

    def _format_sampling_response_for_human(self, result: CreateMessageResult) -> str:
        """Format sampling response for human review"""
        content = (
            result.content.text
            if hasattr(result.content, "text")
            else str(result.content)
        )
        return f"""RESPONSE DETAILS:
- Model: {result.model}
- Role: {result.role}

CONTENT:
{content}"""

    def _parse_human_modified_params(
        self, response: str, original_params: CreateMessageRequestParams
    ) -> tuple[CreateMessageRequestParams | None, str]:
        """Parse human response and return modified params or None if rejected"""
        response_stripped = response.strip().lower()

        if response_stripped == "approve":
            return original_params, ""
        else:
            # Anything else is treated as rejection with reasoning
            rejection_reason = response.strip()
            return None, rejection_reason

    def _parse_human_modified_result(
        self, response: str, original_result: CreateMessageResult
    ) -> tuple[CreateMessageResult | None, str]:
        """Parse human response and return modified result or None if rejected"""
        response_stripped = response.strip().lower()

        if response_stripped == "approve":
            return original_result, ""
        else:
            # Anything else is treated as rejection with reasoning
            rejection_reason = response.strip()
            return None, rejection_reason
