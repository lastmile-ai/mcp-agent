from typing import List, Literal, Optional, TYPE_CHECKING
from pydantic import BaseModel, field_validator

from mcp_agent.tracing.semconv import GEN_AI_REQUEST_TOP_K
from mcp_agent.tracing.telemetry import get_tracer, record_attributes
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams
from mcp_agent.workflows.intent_classifier.intent_classifier_base import (
    Intent,
    IntentClassifier,
    IntentClassificationResult,
)

if TYPE_CHECKING:
    from mcp_agent.core.context import Context

DEFAULT_INTENT_CLASSIFICATION_INSTRUCTION = """
You are a precise intent classifier that analyzes user requests to determine their intended action or purpose.
Below are the available intents with their descriptions and examples:

{context}

Your task is to analyze the following request and determine the most likely intent(s). Consider:
- How well the request matches the intent descriptions and examples
- Any specific entities or parameters that should be extracted
- The confidence level in the classification

Request: {request}

Respond in JSON format:
{{
    "classifications": [
        {{
            "intent": <intent name>,
            "confidence": <"low" | "medium" | "high">,
            "p_score": <float between 0 and 1>,
            "extracted_entities": [
                {{
                    "name": <entity name>,
                    "value": <entity value as string>
                }}
            ],
            "reasoning": <brief explanation>
        }}
    ]
}}

Confidence guidance:
- Use "high" for strong matches (e.g., p_score >= 0.8)
- Use "medium" for moderate matches (e.g., 0.5 <= p_score < 0.8)
- Use "low" for weak matches (e.g., p_score < 0.5)

Return up to {top_k} most likely intents. Only include intents with reasonable confidence (p_score >= 0.5). If no entities are extracted, set "extracted_entities" to an empty array.
If no intents match well, return an empty list.
"""


class LLMIntentClassificationResult(IntentClassificationResult):
    """The result of intent classification using an LLM."""

    confidence: Literal["low", "medium", "high"]
    """Confidence level of the classification"""

    reasoning: str | None = None
    """Optional explanation of why this intent was chosen"""

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        """
        Accept numeric confidences by converting them into discrete levels.
        Maps: [0.0, 0.5) -> "low"; [0.5, 0.8) -> "medium"; [0.8, 1.0] -> "high".
        Also normalizes string case to lower-case.
        """
        try:
            # Handle numeric types (int/float as strings or numbers)
            if isinstance(v, (int, float)):
                score = float(v)
            elif isinstance(v, str):
                # Try to parse as float; if fails, normalize case for string literals
                try:
                    score = float(v)
                except ValueError:
                    return v.strip().lower()
            else:
                return v

            # Quantize numeric score to discrete confidence
            if score >= 0.8:
                return "high"
            elif score >= 0.5:
                return "medium"
            else:
                return "low"
        except Exception:
            # On any unexpected error, return the value as-is and let validation handle it
            return v


class StructuredIntentResponse(BaseModel):
    """The complete structured response from the LLM"""

    classifications: List[LLMIntentClassificationResult]


class LLMIntentClassifier(IntentClassifier):
    """
    An intent classifier that uses an LLM to determine the user's intent.
    Particularly useful when you need:
    - Flexible understanding of natural language
    - Detailed reasoning about classifications
    - Entity extraction alongside classification
    """

    def __init__(
        self,
        llm: AugmentedLLM,
        intents: List[Intent],
        classification_instruction: str | None = None,
        context: Optional["Context"] = None,
        **kwargs,
    ):
        super().__init__(intents=intents, context=context, **kwargs)
        self.llm = llm
        self.classification_instruction = classification_instruction

    @classmethod
    async def create(
        cls,
        llm: AugmentedLLM,
        intents: List[Intent],
        classification_instruction: str | None = None,
    ) -> "LLMIntentClassifier":
        """
        Factory method to create and initialize a classifier.
        Use this instead of constructor since we need async initialization.
        """
        instance = cls(
            llm=llm,
            intents=intents,
            classification_instruction=classification_instruction,
        )
        await instance.initialize()
        return instance

    async def classify(
        self, request: str, top_k: int = 1
    ) -> List[LLMIntentClassificationResult]:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(
            f"{self.__class__.__name__}.classify"
        ) as span:
            if self.context.tracing_enabled:
                span.set_attribute("request", request)
                span.set_attribute("intents", list(self.intents.keys()))
                for intent in self.intents.values():
                    span.set_attribute(
                        f"intent.{intent.name}.description", intent.description
                    )
                    if intent.examples:
                        span.set_attribute(
                            f"intent.{intent.name}.examples", intent.examples
                        )
                    if intent.metadata:
                        record_attributes(
                            span, intent.metadata, f"intent.{intent.name}.metadata"
                        )
                span.set_attribute(GEN_AI_REQUEST_TOP_K, top_k)

            if not self.initialized:
                await self.initialize()

            classification_instruction = (
                self.classification_instruction
                or DEFAULT_INTENT_CLASSIFICATION_INSTRUCTION
            )

            # Generate the context with intent descriptions and examples
            context = self._generate_context()

            # Format the prompt with all the necessary information
            prompt = classification_instruction.format(
                context=context, request=request, top_k=top_k
            )

            span.set_attribute("prompt", prompt)

            # Get classification from LLM
            # Enforce strict schema adherence for structured outputs to reduce type drift
            response = await self.llm.generate_structured(
                message=prompt,
                response_model=StructuredIntentResponse,
                request_params=RequestParams(strict=True),
            )

            if self.context.tracing_enabled:
                response_event_data = {}
                if response and isinstance(response, StructuredIntentResponse):
                    for idx, classification in enumerate(response.classifications):
                        response_event_data.update(
                            self._extract_classification_attributes_for_tracing(
                                classification, f"classification.{idx}"
                            )
                        )

                span.add_event("classification.response", response_event_data)

            if not response or not response.classifications:
                return []

            results = []
            for classification in response.classifications:
                intent = self.intents.get(classification.intent)
                if not intent:
                    span.record_exception(
                        ValueError(f"Invalid intent name '{classification.intent}'")
                    )
                    # Skip invalid categories
                    # TODO: saqadri - log or raise an error
                    continue

                results.append(classification)

            top_results = results[:top_k]

            if self.context.tracing_enabled:
                for idx, classification in enumerate(top_results):
                    span.set_attributes(
                        self._extract_classification_attributes_for_tracing(
                            classification, f"result.{idx}"
                        )
                    )

            return top_results

    def _extract_classification_attributes_for_tracing(
        self, classification: LLMIntentClassificationResult, prefix: str = ""
    ) -> dict:
        """
        Extract attributes from the classification result for tracing.
        This is a placeholder method and can be customized as needed.
        """
        if not self.context.tracing_enabled:
            return {}

        attr_prefix = f"{prefix}." if prefix else ""
        attributes = {
            f"{attr_prefix}intent": classification.intent,
            f"{attr_prefix}confidence": classification.confidence,
        }

        if classification.reasoning:
            attributes[f"{attr_prefix}reasoning"] = classification.reasoning
        if classification.p_score is not None:
            attributes[f"{attr_prefix}p_score"] = classification.p_score

        if classification.extracted_entities:
            for i, entity in enumerate(classification.extracted_entities):
                attributes[f"{attr_prefix}extracted_entities.{i}.name"] = entity.name
                attributes[f"{attr_prefix}extracted_entities.{i}.value"] = entity.value

        return attributes

    def _generate_context(self) -> str:
        """Generate a formatted context string describing all intents"""
        context_parts = []

        for idx, intent in enumerate(self.intents.values(), 1):
            description = (
                f"{idx}. Intent: {intent.name}\nDescription: {intent.description}"
            )

            if intent.examples:
                examples = "\n".join(f"- {example}" for example in intent.examples)
                description += f"\nExamples:\n{examples}"

            if intent.metadata:
                metadata = "\n".join(
                    f"- {key}: {value}" for key, value in intent.metadata.items()
                )
                description += f"\nAdditional Information:\n{metadata}"

            context_parts.append(description)

        return "\n\n".join(context_parts)
