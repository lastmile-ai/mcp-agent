"""
Agent caching for the Deep Orchestrator workflow.

This module provides caching for dynamically created agents to avoid
recreation and reduce costs.
"""

from typing import Dict, List, Optional, Tuple

from mcp_agent.agents.agent import Agent
from mcp_agent.logging.logger import get_logger

logger = get_logger(__name__)


class AgentCache:
    """
    Cache dynamically created agents to avoid recreation.

    Uses LRU (Least Recently Used) eviction policy when cache is full.
    """

    def __init__(self, max_size: int = 50):
        """
        Initialize the agent cache.

        Args:
            max_size: Maximum number of agents to cache
        """
        self.cache: Dict[Tuple[str, ...], Agent] = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def get_key(self, task_desc: str, servers: List[str]) -> Tuple[str, ...]:
        """
        Generate cache key for a task.

        Args:
            task_desc: Task description
            servers: List of required servers

        Returns:
            Cache key tuple
        """
        # Normalize description
        normalized = " ".join(task_desc.lower().split())
        return (normalized, tuple(sorted(servers)))

    def get(self, key: Tuple[str, ...]) -> Optional[Agent]:
        """
        Get agent from cache.

        Args:
            key: Cache key

        Returns:
            Cached agent if found, None otherwise
        """
        agent = self.cache.get(key)
        if agent:
            self.hits += 1
        else:
            self.misses += 1
        return agent

    def put(self, key: Tuple[str, ...], agent: Agent) -> None:
        """
        Add agent to cache with LRU eviction.

        Args:
            key: Cache key
            agent: Agent to cache
        """
        if len(self.cache) >= self.max_size:
            # Remove oldest (first) item
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            # logger.debug(f"Evicted agent from cache: {oldest_key}")

        self.cache[key] = agent
        # logger.debug(f"Cached new agent: {key}")
