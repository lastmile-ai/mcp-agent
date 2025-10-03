import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    EvaluationResult,
    QualityRating,
)


from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM


class DummyLLM(AugmentedLLM):
    def __init__(self, name="Dummy", instruction="Do something.", agent=None):
        super().__init__(name=name, instruction=instruction)
        self.agent = agent or self
        self.history = []
        self._generate_return = ["dummy response"]
        self._generate_structured_return = None
        self._message_str = lambda r, content_only=False: str(r)

    def set_generate_return(self, value):
        self._generate_return = value

    def set_generate_structured_return(self, value):
        self._generate_structured_return = value

    def set_message_str(self, func):
        self._message_str = func

    async def generate(self, message, request_params=None):
        return self._generate_return

    async def generate_structured(self, message, response_model, request_params=None):
        return self._generate_structured_return

    def message_str(self, message, content_only=False):
        return self._message_str(message, content_only)

    async def generate_str(self, message, request_params=None):
        # Minimal implementation for abstract method
        return "\n".join(self.message_str(r) for r in self._generate_return)


class MockToolCallMessage:
    """Mock message that simulates a tool call message with no content"""

    def __init__(self, has_content=False):
        self.content = "Some text content" if has_content else None
        self.tool_calls = ["mock_tool_call"] if not has_content else None

    def __str__(self):
        return self.content if self.content else "[Tool Call]"


@pytest.fixture
def mock_optimizer():
    llm = DummyLLM(name="MockOptimizer", instruction="Optimize this.")
    llm.set_generate_return(["optimized response"])
    llm.set_generate_structured_return(None)
    llm.set_message_str(lambda r: str(r))
    return llm


@pytest.fixture
def mock_evaluator():
    llm = DummyLLM(name="MockEvaluator", instruction="Evaluate this.")
    llm.set_generate_structured_return(
        EvaluationResult(
            rating=QualityRating.EXCELLENT,
            feedback="Looks good.",
            needs_improvement=False,
            focus_areas=[],
        )
    )
    return llm


def test_initialization_with_augmented_llm(mock_optimizer, mock_evaluator):
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
        name="TestEO",
        min_rating=QualityRating.GOOD,
        max_refinements=2,
    )
    assert eo.optimizer == mock_optimizer
    assert eo.evaluator == mock_evaluator
    assert eo.min_rating == QualityRating.GOOD
    assert eo.max_refinements == 2
    assert eo.name == "TestEO"


def test_build_eval_prompt(mock_optimizer, mock_evaluator):
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
    )
    prompt = eo._build_eval_prompt(
        original_request="What is the capital of France?",
        current_response="Paris",
        iteration=0,
    )
    assert "Evaluate the following response" in prompt
    assert "Original Request: What is the capital of France?" in prompt
    assert "Current Response (Iteration 1): Paris" in prompt
    assert "Provide your evaluation as a structured response" in prompt


def test_build_refinement_prompt(mock_optimizer, mock_evaluator):
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
    )
    feedback = EvaluationResult(
        rating=QualityRating.FAIR,
        feedback="Needs more detail.",
        needs_improvement=True,
        focus_areas=["Add more facts"],
    )
    prompt = eo._build_refinement_prompt(
        original_request="What is the capital of France?",
        current_response="Paris",
        feedback=feedback,
        iteration=1,
    )
    assert "Improve your previous response" in prompt
    assert "Original Request: What is the capital of France?" in prompt
    assert "Previous Response (Iteration 2):" in prompt
    assert "Quality Rating: 1" in prompt
    assert "Feedback: Needs more detail." in prompt
    assert "Areas to Focus On: Add more facts" in prompt


@pytest.mark.asyncio
async def test_generate_refinement_loop(monkeypatch, mock_optimizer, mock_evaluator):
    # Simulate evaluator returning needs_improvement=True, then needs_improvement=False
    first_result = EvaluationResult(
        rating=QualityRating.FAIR,
        feedback="Add more detail.",
        needs_improvement=True,
        focus_areas=["Be specific"],
    )
    second_result = EvaluationResult(
        rating=QualityRating.EXCELLENT,
        feedback="Perfect.",
        needs_improvement=False,
        focus_areas=[],
    )
    # Patch generate_structured to return first_result, then second_result
    mock_evaluator.generate_structured = AsyncMock(
        side_effect=[first_result, second_result]
    )

    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
        min_rating=QualityRating.GOOD,
        max_refinements=3,
    )

    # Patch optimizer_llm.generate to return different responses for each refinement
    mock_optimizer.generate = AsyncMock(
        side_effect=[
            ["initial response"],  # First call
            ["refined response"],  # Second call
        ]
    )

    result = await eo.generate("Test prompt")
    # Should return the best response, which is the second one (EXCELLENT)
    assert result == ["refined response"]
    # Should have two entries in refinement_history
    assert len(eo.refinement_history) == 2
    assert eo.refinement_history[0]["evaluation_result"].needs_improvement is True
    assert eo.refinement_history[1]["evaluation_result"].needs_improvement is False


@pytest.mark.asyncio
async def test_generate_str_returns_string(mock_optimizer, mock_evaluator):
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
    )
    # Patch optimizer_llm.generate to return a list of responses
    mock_optimizer.generate = AsyncMock(return_value=["foo", "bar"])

    # Patch message_str to join responses
    def mock_message_str(msg, content_only=False):
        return msg.upper()

    mock_optimizer.message_str = MagicMock(side_effect=mock_message_str)
    result = await eo.generate_str("Prompt")
    # Should join the responses with newline and apply message_str
    assert result == "FOO\nBAR"


@pytest.mark.asyncio
async def test_generate_str_filters_empty_messages(mock_optimizer, mock_evaluator):
    """Test that generate_str properly filters out messages with no content (e.g., tool calls)"""
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
    )

    # Create mock messages: one with content, one without (tool call), one with content
    message_with_content_1 = MockToolCallMessage(has_content=True)
    message_with_tool_call = MockToolCallMessage(
        has_content=False
    )  # No content, has tool call
    message_with_content_2 = MockToolCallMessage(has_content=True)

    # Set up the optimizer to return these mixed messages
    mock_optimizer.generate = AsyncMock(
        return_value=[
            message_with_content_1,
            message_with_tool_call,
            message_with_content_2,
        ]
    )

    # Set up message_str to behave like OpenAI's implementation:
    # - Return empty string for messages without content
    # - Return actual content for messages with content
    def mock_message_str(msg, content_only=False):
        if hasattr(msg, "content") and msg.content:
            return msg.content
        return ""  # Empty string for tool calls or messages without content

    mock_optimizer.message_str = MagicMock(side_effect=mock_message_str)

    result = await eo.generate_str("Test prompt")

    # Should only include messages with content, filtering out empty strings
    assert result == "Some text content\nSome text content"

    # Verify message_str was called for each message
    assert mock_optimizer.message_str.call_count == 3


@pytest.mark.asyncio
async def test_generate_str_handles_all_empty_messages(mock_optimizer, mock_evaluator):
    """Test that generate_str handles the case where all messages are empty (all tool calls)"""
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
    )

    # Create mock messages that are all tool calls (no content)
    tool_call_messages = [MockToolCallMessage(has_content=False) for _ in range(3)]

    mock_optimizer.generate = AsyncMock(return_value=tool_call_messages)

    # Mock message_str to return empty strings for tool calls
    def mock_empty_message_str(msg, content_only=False):
        return ""

    mock_optimizer.message_str = MagicMock(side_effect=mock_empty_message_str)

    result = await eo.generate_str("Test prompt")

    # Should return empty string when all messages are filtered out
    assert result == ""


@pytest.mark.asyncio
async def test_generate_structured_delegates_to_optimizer(
    mock_optimizer, mock_evaluator
):
    eo = EvaluatorOptimizerLLM(
        optimizer=mock_optimizer,
        evaluator=mock_evaluator,
    )
    # Patch generate_str to return a string
    eo.generate_str = AsyncMock(return_value="structured input")
    # Patch optimizer.generate_structured to return a model instance
    expected = EvaluationResult(
        rating=QualityRating.GOOD,
        feedback="Solid.",
        needs_improvement=False,
        focus_areas=[],
    )
    mock_optimizer.generate_structured = AsyncMock(return_value=expected)
    result = await eo.generate_structured(
        message="Prompt",
        response_model=EvaluationResult,
        request_params={"foo": "bar"},
    )
    assert result == expected
    mock_optimizer.generate_structured.assert_awaited_once_with(
        message="structured input",
        response_model=EvaluationResult,
        request_params={"foo": "bar"},
    )
