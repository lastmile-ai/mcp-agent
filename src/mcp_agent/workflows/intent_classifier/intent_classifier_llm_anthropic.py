from typing import List, Optional, TYPE_CHECKING

from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.workflows.intent_classifier.intent_classifier_base import Intent
from mcp_agent.workflows.intent_classifier.intent_classifier_llm import (
    LLMIntentClassifier,
)

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

CLASSIFIER_SYSTEM_INSTRUCTION = """
You are a precise intent classifier that analyzes input requests to determine their intended action or purpose.
You are provided with a request and a list of intents to choose from.
You can choose one or more intents, or choose none if no intent is appropriate.
"""


class AnthropicLLMIntentClassifier(LLMIntentClassifier):
    """
    An LLM router that uses an Anthropic model to make routing decisions.
    """

    def __init__(
        self,
        intents: List[Intent],
        classification_instruction: str | None = None,
        name: str | None = None,
        llm: AnthropicAugmentedLLM | None = None,
        request_params: RequestParams | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        anthropic_llm = llm or AnthropicAugmentedLLM(
            name=name,
            instruction=CLASSIFIER_SYSTEM_INSTRUCTION,
            default_request_params=request_params,
            context=context,
        )

        super().__init__(
            llm=anthropic_llm,
            intents=intents,
            classification_instruction=classification_instruction,
            context=context,
            **kwargs,
        )

    @classmethod
    async def create(
        cls,
        llm: AnthropicAugmentedLLM,
        intents: List[Intent],
        classification_instruction: str | None = None,
        name: str | None = None,
        request_params: RequestParams | None = None,
        context: Optional["Context"] = None,
    ) -> "AnthropicLLMIntentClassifier":
        """
        Factory method to create and initialize a classifier.
        Use this instead of constructor since we need async initialization.
        """
        instance = cls(
            llm=llm,
            intents=intents,
            classification_instruction=classification_instruction,
            name=name,
            request_params=request_params,
            context=context,
        )
        await instance.initialize()
        return instance
