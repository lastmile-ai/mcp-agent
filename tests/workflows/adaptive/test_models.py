"""
Tests for Adaptive Workflow V2 Models
"""

import pytest
from datetime import datetime, timezone

from mcp_agent.workflows.adaptive.models import (
    TaskType,
    ResearchAspect,
    SubagentResult,
    SynthesisDecision,
    ExecutionMemory,
    ExecutionResult,
)


class TestTaskType:
    """Tests for TaskType enum"""

    def test_task_type_values(self):
        """Test TaskType enum values"""
        assert TaskType.RESEARCH.value == "research"
        assert TaskType.ACTION.value == "action"
        assert TaskType.HYBRID.value == "hybrid"

    def test_task_type_comparison(self):
        """Test TaskType comparison"""
        assert TaskType.RESEARCH == TaskType.RESEARCH
        assert TaskType.RESEARCH != TaskType.ACTION


class TestResearchAspect:
    """Tests for ResearchAspect model"""

    def test_research_aspect_creation(self):
        """Test creating ResearchAspect with all fields"""
        aspect = ResearchAspect(
            name="Web Research",
            objective="Find information about AI",
            required_servers=["web_search", "fetch"],
            use_predefined_agent="WebSearcher",
        )

        assert aspect.name == "Web Research"
        assert aspect.objective == "Find information about AI"
        assert len(aspect.required_servers) == 2
        assert aspect.use_predefined_agent == "WebSearcher"

    def test_research_aspect_defaults(self):
        """Test ResearchAspect with default values"""
        aspect = ResearchAspect(name="Simple Research", objective="Basic task")

        assert aspect.required_servers == []
        assert aspect.use_predefined_agent is None

    def test_research_aspect_validation(self):
        """Test ResearchAspect field validation"""
        # Should require name and objective
        with pytest.raises(ValueError):
            ResearchAspect()

        with pytest.raises(ValueError):
            ResearchAspect(name="Test")

        with pytest.raises(ValueError):
            ResearchAspect(objective="Test")


class TestSubagentResult:
    """Tests for SubagentResult model"""

    def test_subagent_result_success(self):
        """Test creating successful SubagentResult"""
        start = datetime.now(timezone.utc)
        end = datetime.now(timezone.utc)

        result = SubagentResult(
            aspect_name="Test Aspect",
            findings="Found important information",
            success=True,
            start_time=start,
            end_time=end,
            cost=1.5,
        )

        assert result.aspect_name == "Test Aspect"
        assert result.findings == "Found important information"
        assert result.success is True
        assert result.error is None
        assert result.cost == 1.5

    def test_subagent_result_failure(self):
        """Test creating failed SubagentResult"""
        result = SubagentResult(
            aspect_name="Failed Aspect",
            success=False,
            error="Connection timeout",
            start_time=datetime.now(timezone.utc),
        )

        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.findings is None
        assert result.end_time is None

    def test_subagent_result_defaults(self):
        """Test SubagentResult default values"""
        result = SubagentResult(
            aspect_name="Default Test", start_time=datetime.now(timezone.utc)
        )

        assert result.success is False
        assert result.cost == 0.0
        assert result.findings is None
        assert result.error is None


class TestSynthesisDecision:
    """Tests for SynthesisDecision model"""

    def test_synthesis_decision_complete(self):
        """Test SynthesisDecision indicating completion"""
        decision = SynthesisDecision(
            is_complete=True,
            confidence=0.95,
            reasoning="All objectives have been thoroughly addressed",
        )

        assert decision.is_complete is True
        assert decision.confidence == 0.95
        assert decision.new_aspects is None

    def test_synthesis_decision_continue(self):
        """Test SynthesisDecision with new aspects to research"""
        new_aspects = [
            ResearchAspect(name="Aspect 1", objective="Research more"),
            ResearchAspect(name="Aspect 2", objective="Investigate further"),
        ]

        decision = SynthesisDecision(
            is_complete=False,
            confidence=0.6,
            reasoning="Need more information",
            new_aspects=new_aspects,
        )

        assert decision.is_complete is False
        assert len(decision.new_aspects) == 2
        assert decision.new_aspects[0].name == "Aspect 1"

    def test_synthesis_decision_confidence_bounds(self):
        """Test confidence value bounds"""
        # Valid confidence
        decision = SynthesisDecision(is_complete=True, confidence=0.5, reasoning="Test")
        assert decision.confidence == 0.5

        # Test bounds validation
        with pytest.raises(ValueError):
            SynthesisDecision(
                is_complete=True,
                confidence=1.5,  # > 1.0
                reasoning="Test",
            )

        with pytest.raises(ValueError):
            SynthesisDecision(
                is_complete=True,
                confidence=-0.1,  # < 0.0
                reasoning="Test",
            )


class TestExecutionMemory:
    """Tests for ExecutionMemory model"""

    def test_execution_memory_creation(self):
        """Test creating ExecutionMemory"""
        memory = ExecutionMemory(
            execution_id="test-123",
            objective="Test objective",
            task_type=TaskType.RESEARCH,
        )

        assert memory.execution_id == "test-123"
        assert memory.objective == "Test objective"
        assert memory.task_type == TaskType.RESEARCH
        assert memory.iterations == 0
        assert memory.total_cost == 0.0
        assert isinstance(memory.start_time, datetime)

    def test_execution_memory_with_history(self):
        """Test ExecutionMemory with research history"""
        # Create with message-like objects
        history = [["First synthesis message"], ["Second synthesis message"]]

        memory = ExecutionMemory(
            execution_id="test-456",
            objective="Complex research",
            task_type=TaskType.HYBRID,
            iterations=2,
            research_history=history,
            total_cost=5.0,
        )

        assert len(memory.research_history) == 2
        assert memory.iterations == 2
        assert memory.total_cost == 5.0

    def test_execution_memory_with_results(self):
        """Test ExecutionMemory with subagent results"""
        results = [
            SubagentResult(
                aspect_name="Result 1",
                success=True,
                start_time=datetime.now(timezone.utc),
                cost=1.0,
            ),
            SubagentResult(
                aspect_name="Result 2",
                success=False,
                start_time=datetime.now(timezone.utc),
                cost=0.5,
            ),
        ]

        memory = ExecutionMemory(
            execution_id="test-789",
            objective="Test with results",
            subagent_results=results,
            total_cost=1.5,
        )

        assert len(memory.subagent_results) == 2
        assert memory.subagent_results[0].success is True
        assert memory.subagent_results[1].success is False


class TestExecutionResult:
    """Tests for ExecutionResult model"""

    def test_execution_result_creation(self):
        """Test creating ExecutionResult"""
        # Mock messages
        mock_messages = ["Result message 1", "Result message 2"]

        result = ExecutionResult(
            execution_id="result-123",
            objective="Generate report",
            task_type=TaskType.RESEARCH,
            result_messages=mock_messages,
            confidence=0.85,
            iterations=5,
            subagents_used=3,
            total_time_seconds=120.5,
            total_cost=8.0,
        )

        assert result.execution_id == "result-123"
        assert result.result_messages == mock_messages
        assert result.confidence == 0.85
        assert result.success is True
        assert result.limitations == []

    def test_execution_result_with_limitations(self):
        """Test ExecutionResult with limitations"""
        result = ExecutionResult(
            execution_id="limited-result",
            objective="Partial completion",
            task_type=TaskType.ACTION,
            result_messages=["Partial result"],
            confidence=0.6,
            iterations=10,
            subagents_used=5,
            total_time_seconds=300.0,
            total_cost=15.0,
            success=False,
            limitations=["Could not access required API", "Time budget exceeded"],
        )

        assert result.success is False
        assert len(result.limitations) == 2
        assert "Time budget exceeded" in result.limitations

    def test_execution_result_message_flexibility(self):
        """Test that result_messages can handle various types"""
        # Test with different message formats
        various_messages = [
            {"role": "assistant", "content": "Message 1"},
            ["Nested", "messages"],
            "Simple string message",
        ]

        result = ExecutionResult(
            execution_id="flex-messages",
            objective="Test flexibility",
            task_type=TaskType.HYBRID,
            result_messages=various_messages,
            confidence=0.9,
            iterations=1,
            subagents_used=1,
            total_time_seconds=10.0,
            total_cost=1.0,
        )

        assert result.result_messages == various_messages
        assert isinstance(result.result_messages, list)


class TestModelSerialization:
    """Tests for model serialization/deserialization"""

    def test_execution_memory_serialization(self):
        """Test ExecutionMemory can be serialized to dict"""
        memory = ExecutionMemory(
            execution_id="serialize-test",
            objective="Test serialization",
            task_type=TaskType.RESEARCH,
            iterations=3,
            total_cost=5.0,
        )

        # Add some data
        memory.research_history.append(["Synthesis 1"])
        memory.subagent_results.append(
            SubagentResult(
                aspect_name="Test", success=True, start_time=datetime.now(timezone.utc)
            )
        )

        # Serialize
        data = memory.model_dump(mode="json")

        assert data["execution_id"] == "serialize-test"
        assert data["task_type"] == "research"
        assert len(data["research_history"]) == 1
        assert len(data["subagent_results"]) == 1

        # Deserialize
        loaded = ExecutionMemory(**data)
        assert loaded.execution_id == memory.execution_id
        assert loaded.task_type == memory.task_type

    def test_execution_result_serialization(self):
        """Test ExecutionResult serialization with message handling"""
        result = ExecutionResult(
            execution_id="result-serial",
            objective="Test",
            task_type=TaskType.ACTION,
            result_messages=[{"content": "Test message"}],
            confidence=0.8,
            iterations=2,
            subagents_used=1,
            total_time_seconds=50.0,
            total_cost=3.0,
        )

        # Serialize
        data = result.model_dump()

        assert data["execution_id"] == "result-serial"
        assert data["result_messages"] == [{"content": "Test message"}]

        # Should be able to handle the Any type
        assert "result_messages" in data
