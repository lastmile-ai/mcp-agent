from unittest.mock import MagicMock

from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.deep_orchestrator.cache import AgentCache


def test_cache_hit_preserves_recently_used_agent() -> None:
    """Reading an older entry protects it from the next capacity eviction."""
    cache = AgentCache(max_size=2)
    first_key = cache.get_key("first task", ["server"])
    second_key = cache.get_key("second task", ["server"])
    third_key = cache.get_key("third task", ["server"])
    first = MagicMock(spec=Agent)
    second = MagicMock(spec=Agent)
    third = MagicMock(spec=Agent)
    cache.put(first_key, first)
    cache.put(second_key, second)

    assert cache.get(first_key) is first
    cache.put(third_key, third)

    assert cache.get(first_key) is first
    assert cache.get(second_key) is None
    assert cache.get(third_key) is third
    assert cache.hits == 3
    assert cache.misses == 1


def test_replacing_cached_agent_does_not_evict_another_agent() -> None:
    """Updating a full cache retains unrelated entries and its capacity."""
    cache = AgentCache(max_size=2)
    first_key = cache.get_key("first task", [])
    second_key = cache.get_key("second task", [])
    first = MagicMock(spec=Agent)
    replacement = MagicMock(spec=Agent)
    cache.put(first_key, first)
    cache.put(second_key, MagicMock(spec=Agent))

    cache.put(second_key, replacement)

    assert cache.get(first_key) is first
    assert cache.get(second_key) is replacement
    assert len(cache.cache) == 2


def test_replacing_cached_agent_refreshes_recency() -> None:
    """A replacement becomes most recently used before the next insertion."""
    cache = AgentCache(max_size=2)
    first_key = cache.get_key("first task", [])
    second_key = cache.get_key("second task", [])
    third_key = cache.get_key("third task", [])
    replacement = MagicMock(spec=Agent)
    cache.put(first_key, MagicMock(spec=Agent))
    cache.put(second_key, MagicMock(spec=Agent))

    cache.put(first_key, replacement)
    cache.put(third_key, MagicMock(spec=Agent))

    assert cache.get(first_key) is replacement
    assert cache.get(second_key) is None
