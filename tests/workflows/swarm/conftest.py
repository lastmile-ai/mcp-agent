import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.types import CallToolResult, TextContent

from mcp_agent.agents.agent import Agent
from mcp_agent.core.context import Context
from mcp_agent.workflows.swarm.swarm import SwarmAgent, AgentFunctionResult, DoneAgent


@pytest.fixture
def mock_agent():
    """Mock basic agent fixture"""
    agent = MagicMock(spec=Agent)
    agent.name = "test_agent"
    agent.instruction = "Test instruction"
    agent.call_tool = AsyncMock()
    agent.initialize = AsyncMock()
    agent.shutdown = AsyncMock()
    agent.functions = []
    return agent


@pytest.fixture
def mock_swarm_agent():
    """Mock swarm agent fixture"""
    agent = MagicMock(spec=SwarmAgent)
    agent.name = "test_swarm_agent"
    agent.instruction = "Test swarm instruction"
    agent.call_tool = AsyncMock()
    agent.initialize = AsyncMock()
    agent.shutdown = AsyncMock()
    agent.parallel_tool_calls = False
    agent.functions = []
    agent.context = Context()
    agent._function_tool_map = {}
    return agent


@pytest.fixture
def done_agent():
    """Create a real DoneAgent instance for testing"""
    return DoneAgent()


@pytest.fixture
def test_function_result():
    """Test function that returns a string"""
    return "test_function_result"


@pytest.fixture
def test_function_agent_result(mock_swarm_agent):
    """Test function that returns an agent"""
    return mock_swarm_agent


@pytest.fixture
def test_function_agent_function_result():
    """Test function that returns an AgentFunctionResult"""
    return AgentFunctionResult(value="test_function_result")


@pytest.fixture
def test_function_none_result():
    """Test function that returns None"""
    return None


@pytest.fixture
def mock_tool_response():
    """Mock tool response"""
    return CallToolResult(content=[TextContent(type="text", text="Mock tool response")])
