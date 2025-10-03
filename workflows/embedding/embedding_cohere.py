from typing import List, Optional, TYPE_CHECKING

from cohere import Client
from numpy import array, float32

from mcp_agent.tracing.semconv import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)
from mcp_agent.tracing.telemetry import get_tracer
from mcp_agent.workflows.embedding.embedding_base import EmbeddingModel, FloatArray

if TYPE_CHECKING:
    from mcp_agent.core.context import Context


class CohereEmbeddingModel(EmbeddingModel):
    """Cohere embedding model implementation"""

    def __init__(
        self,
        model: str = "embed-multilingual-v3.0",
        context: Optional["Context"] = None,
        **kwargs,
    ):
        super().__init__(context=context, **kwargs)
        self.client = Client(api_key=self.context.config.cohere.api_key)
        self.model = model
        # Cache the dimension since it's fixed per model
        # https://docs.cohere.com/v2/docs/cohere-embed
        self._embedding_dim = {
            "embed-english-v2.0": 4096,
            "embed-english-light-v2.0": 1024,
            "embed-english-v3.0": 1024,
            "embed-english-light-v3.0": 384,
            "embed-multilingual-v2.0": 768,
            "embed-multilingual-v3.0": 1024,
            "embed-multilingual-light-v3.0": 384,
        }[model]

    async def embed(self, data: List[str]) -> FloatArray:
        tracer = get_tracer(self.context)
        with tracer.start_as_current_span(f"{self.__class__.__name__}.embed") as span:
            span.set_attribute(GEN_AI_REQUEST_MODEL, self.model)
            span.set_attribute(GEN_AI_OPERATION_NAME, "embeddings")
            span.set_attribute("data", data)
            span.set_attribute("embedding_dim", self.embedding_dim)

            response = self.client.embed(
                texts=data,
                model=self.model,
                input_type="classification",
                embedding_types=["float"],
            )

            if response.meta and response.meta.tokens:
                if response.meta.tokens.input_tokens:
                    span.set_attribute(
                        GEN_AI_USAGE_INPUT_TOKENS, response.meta.tokens.input_tokens
                    )
                if response.meta.tokens.output_tokens:
                    span.set_attribute(
                        GEN_AI_USAGE_OUTPUT_TOKENS, response.meta.tokens.output_tokens
                    )

            embeddings = array(response.embeddings, dtype=float32)
            return embeddings

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim
