from typing import List, Optional, TYPE_CHECKING

from numpy import array, float32, stack
from openai import OpenAI

from mcp_agent.tracing.semconv import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
)
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.workflows.embedding.embedding_base import EmbeddingModel, FloatArray

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class OpenAIEmbeddingModel(EmbeddingModel):
    """OpenAI embedding model implementation"""

    def __init__(
        self, model: str = "text-embedding-3-small", context: Optional["Context"] = None
    ):
        super().__init__(context=context)
        self.client = OpenAI(api_key=self.context.config.openai.api_key)
        self.model = model
        # Cache the dimension since it's fixed per model
        self._embedding_dim = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }[model]

    async def embed(self, data: List[str]) -> FloatArray:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(f"{self.__class__.__name__}.embed") as span:
            span.set_attribute(GEN_AI_REQUEST_MODEL, self.model)
            span.set_attribute(GEN_AI_OPERATION_NAME, "embeddings")
            span.set_attribute("data", data)
            span.set_attribute("embedding_dim", self.embedding_dim)

            response = self.client.embeddings.create(
                model=self.model, input=data, encoding_format="float"
            )

            span.set_attribute(GEN_AI_RESPONSE_MODEL, response.model)
            if response.usage:
                if response.usage.prompt_tokens is not None:
                    span.set_attribute(
                        GEN_AI_USAGE_INPUT_TOKENS, response.usage.prompt_tokens
                    )
                if response.usage.total_tokens is not None:
                    span.set_attribute(
                        "gen_ai.usage.total_tokens", response.usage.total_tokens
                    )

            # Sort the embeddings by their index to ensure correct order
            sorted_embeddings = sorted(response.data, key=lambda x: x.index)

            # Stack all embeddings into a single array
            embeddings = stack(
                [
                    array(embedding.embedding, dtype=float32)
                    for embedding in sorted_embeddings
                ]
            )
            return embeddings

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim
