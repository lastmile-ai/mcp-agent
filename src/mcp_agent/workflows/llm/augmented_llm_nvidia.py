from typing import AsyncIterator, Type

from mcp_agent.workflows.llm.augmented_llm import ModelT, RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.streaming_events import StreamEvent


class NvidiaAugmentedLLM(OpenAIAugmentedLLM):
    """
    NVIDIA NIM implementation using OpenAI-compatible API.

    NVIDIA NIM provides OpenAI API compatibility at https://integrate.api.nvidia.com/v1
    (or a self-hosted NIM endpoint) including chat completions, tool calling,
    and structured outputs.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Override provider name for logging and telemetry
        self.provider = "NVIDIA"

    async def select_model(
        self, request_params: RequestParams | None = None
    ) -> str | None:
        """
        Select model for NVIDIA, prioritizing config default_model over benchmarks.
        """
        # Check request_params first
        if request_params and request_params.model:
            return request_params.model

        # Check NVIDIA config default_model
        nvidia_config = self.get_provider_config(self.context)
        if nvidia_config and nvidia_config.default_model:
            return nvidia_config.default_model

        # Fall back to parent's model selection (benchmarks)
        return await super().select_model(request_params)

    async def generate_structured(
        self,
        message,
        response_model: Type[ModelT],
        request_params: RequestParams | None = None,
    ) -> ModelT:
        """
        Generate structured output. For structured outputs with tool calling (unsupported by API),
        uses a two-step approach:
        1. Generate response with tool calls (get real data)
        2. Generate structured output response
        """
        text_response = await self.generate_str(
            message=message,
            request_params=request_params,
        )

        format_prompt = f"""Based on the following information, provide a response in JSON format.

Information:
{text_response}

Return ONLY valid JSON matching this exact structure. Do not include any explanation or additional text."""

        result = await super().generate_structured(
            message=format_prompt,
            response_model=response_model,
            request_params=request_params,
        )

        return result

    async def generate_stream(
        self,
        message,
        request_params: RequestParams | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Streaming is not implemented for NVIDIA yet (the OpenAI base class does
        not implement it either). Use generate / generate_str instead.
        """
        raise NotImplementedError("Streaming not implemented for this provider")

    @classmethod
    def get_provider_config(cls, context):
        """
        Get NVIDIA configuration from context.

        Returns the nvidia settings instead of openai settings,
        allowing separate configuration for NVIDIA.
        """
        return getattr(getattr(context, "config", None), "nvidia", None)
