from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM


class LMStudioAugmentedLLM(OpenAIAugmentedLLM):
    """
    LM Studio implementation using OpenAI-compatible API.

    LM Studio provides full OpenAI API compatibility at http://localhost:1234/v1
    including chat completions, tool calling, and structured outputs.

    This implementation extends OpenAIAugmentedLLM directly since LM Studio's API
    is fully compatible with OpenAI's chat completions endpoint.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Override provider name for logging and telemetry
        self.provider = "LM Studio"

    @classmethod
    def get_provider_config(cls, context):
        """
        Get LM Studio configuration from context.

        Returns the lm_studio settings instead of openai settings,
        allowing separate configuration for LM Studio.
        """
        return getattr(getattr(context, "config", None), "lm_studio", None)
