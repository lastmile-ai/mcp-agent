from typing import Type

from mcp_agent.workflows.llm.augmented_llm import ModelT, RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


class LMStudioAugmentedLLM(OpenAIAugmentedLLM):
    """
    LM Studio implementation using OpenAI-compatible API.

    LM Studio provides full OpenAI API compatibility at http://localhost:1234/v1
    including chat completions, tool calling, and structured outputs.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Override provider name for logging and telemetry
        self.provider = "LM Studio"

    async def select_model(
        self, request_params: RequestParams | None = None
    ) -> str | None:
        """
        Select model for LM Studio, prioritizing config default_model over benchmarks.
        """
        # Check request_params first
        if request_params and request_params.model:
            return request_params.model

        # Check LM Studio config default_model
        lm_studio_config = self.get_provider_config(self.context)
        if lm_studio_config and lm_studio_config.default_model:
            return lm_studio_config.default_model

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

    @classmethod
    def get_provider_config(cls, context):
        """
        Get LM Studio configuration from context.

        Returns the lm_studio settings instead of openai settings,
        allowing separate configuration for LM Studio.
        """
        return getattr(getattr(context, "config", None), "lm_studio", None)
