from abc import ABC, abstractmethod
from typing import Dict, List, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

from mcp_agent.core.context_dependent import ContextDependent

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class Intent(BaseModel):
    """A class that represents a single intent category"""

    name: str
    """The name of the intent"""

    description: str | None = None
    """A description of what this intent represents"""

    examples: List[str] = Field(default_factory=list)
    """Example phrases or requests that match this intent"""

    metadata: Dict[str, str] = Field(default_factory=dict)
    """Additional metadata about the intent that might be useful for classification"""


class ExtractedEntity(BaseModel):
    """A single extracted entity from the request"""

    name: str
    """Entity name/key"""

    value: str | None = None
    """Entity value as a string"""


class IntentClassificationResult(BaseModel):
    """A class that represents the result of intent classification"""

    intent: str
    """The classified intent name"""

    p_score: float | None = None
    """
    The probability score (i.e. 0->1) of the classification. 
    This is optional and may only be provided if the classifier is probabilistic (e.g. a probabilistic binary classifier).
    """

    extracted_entities: Optional[List[ExtractedEntity]] = Field(default_factory=list)
    """Any entities or parameters extracted from the input request that are relevant to the intent"""


class IntentClassifier(ABC, ContextDependent):
    """
    Base class for intent classification. This can be implemented using different approaches
    like LLMs, embedding models, traditional ML classification models, or rule-based systems.

    When to use this:
        - When you need to understand the user's intention before routing or processing
        - When you want to extract structured information from natural language inputs
        - When you need to handle multiple related but distinct types of requests

    Examples:
        - Classifying customer service requests (complaint, question, feedback)
        - Understanding user commands in a chat interface
        - Determining the type of analysis requested for a dataset
    """

    def __init__(
        self, intents: List[Intent], context: Optional["Context"] = None, **kwargs
    ):
        super().__init__(context=context, **kwargs)
        self.intents = {intent.name: intent for intent in intents}
        self.initialized: bool = False

        if not self.intents:
            raise ValueError("At least one intent must be provided")

    @abstractmethod
    async def classify(
        self, request: str, top_k: int = 1
    ) -> List[IntentClassificationResult]:
        """
        Classify the input request into one or more intents.

        Args:
            request: The input text to classify
            top_k: Maximum number of top intent matches to return. May return fewer.

        Returns:
            List of classification results, ordered by confidence
        """

    async def initialize(self):
        """Initialize the classifier. Override this method if needed."""
        self.initialized = True


# Example
# Define some intents
# intents = [
#     Intent(
#         name="schedule_meeting",
#         description="Schedule or set up a meeting or appointment",
#         examples=[
#             "Can you schedule a meeting with John?",
#             "Set up a call for next week",
#             "I need to arrange a meeting"
#         ]
#     ),
#     Intent(
#         name="check_calendar",
#         description="Check calendar availability or existing appointments",
#         examples=[
#             "What meetings do I have today?",
#             "Show me my calendar",
#             "Am I free tomorrow afternoon?"
#         ]
#     )
# ]

# # Initialize with OpenAI embeddings
# classifier = OpenAIEmbeddingIntentClassifier(intents=intents, model="text-embedding-3-small")

# # Or use Cohere embeddings
# classifier = OpenAIEmbeddingIntentClassifier(intents=intents, model="embed-multilingual-v3.0")

# # Classify some text
# results = await classifier.classify(
#     request="Can you set up a meeting with Sarah for tomorrow?"
#     top_k=3
# )
