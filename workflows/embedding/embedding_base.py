from abc import ABC, abstractmethod
from typing import Dict, List

from numpy import float32
from numpy.typing import NDArray
from sklearn.metrics.pairwise import cosine_similarity

from mcp_agent.core.context_dependent import ContextDependent


FloatArray = NDArray[float32]


class EmbeddingModel(ABC, ContextDependent):
    """Abstract interface for embedding models"""

    @abstractmethod
    async def embed(self, data: List[str]) -> FloatArray:
        """
        Generate embeddings for a list of messages

        Args:
            data: List of text strings to embed

        Returns:
            Array of embeddings, shape (len(texts), embedding_dim)
        """

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Return the dimensionality of the embeddings"""


def compute_similarity_scores(
    embedding_a: FloatArray, embedding_b: FloatArray
) -> Dict[str, float]:
    """
    Compute different similarity metrics between embeddings
    """
    # Reshape for sklearn's cosine_similarity
    a_emb = embedding_a.reshape(1, -1)
    b_emb = embedding_b.reshape(1, -1)

    cosine_sim = float(cosine_similarity(a_emb, b_emb)[0, 0])

    # Could add other similarity metrics here
    return {
        "cosine": cosine_sim,
        # "euclidean": float(euclidean_similarity),
        # "dot_product": float(dot_product)
    }


def compute_confidence(similarity_scores: Dict[str, float]) -> float:
    """
    Compute overall confidence score from individual similarity metrics
    """
    # For now, just use cosine similarity as confidence
    # Could implement more sophisticated combination of scores
    return similarity_scores["cosine"]
