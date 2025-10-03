import inspect
import pytest
from typing import Type
from unittest.mock import Mock

from crewai.tools import BaseTool as CrewaiBaseTool, tool
from mcp.server.fastmcp.tools import Tool as FastTool
from pydantic import BaseModel, Field

from mcp_agent.tools.crewai_tool import (
    from_crewai_tool,
    _create_function_from_schema,
)


# Test fixtures - custom tools for testing
@tool
def sample_multiply_tool(first_number: int, second_number: int) -> str:
    """Multiply two numbers together."""
    return str(first_number * second_number)


@tool
def sample_no_args_tool() -> str:
    """A tool that takes no arguments."""
    return "Hello World"


class MultiplyToolInput(BaseModel):
    """Input schema for MultiplyTool."""

    first_number: float = Field(..., description="First number")
    second_number: float = Field(..., description="Second number")


class MultiplyTool(CrewaiBaseTool):
    """A custom multiply tool for testing class-based CrewAI tools."""

    name: str = "multiply"
    description: str = "Multiply two numbers"
    args_schema: Type[BaseModel] = MultiplyToolInput

    def _run(self, first_number: float, second_number: float) -> float:
        return first_number * second_number


class GreetToolInput(BaseModel):
    """Input schema for GreetTool."""

    name: str = Field(..., description="Name to greet")
    greeting: str = Field(default="Hello", description="Greeting to use")


class GreetTool(CrewaiBaseTool):
    """A custom greet tool for testing optional parameters."""

    name: str = "greet"
    description: str = "Greet someone with a custom message"
    args_schema: Type[BaseModel] = GreetToolInput

    def _run(self, name: str, greeting: str = "Hello") -> str:
        return f"{greeting}, {name}!"


class NoArgsToolSchema(BaseModel):
    """Empty schema for tools with no arguments."""

    pass


class NoArgsTool(CrewaiBaseTool):
    """A tool with no arguments for testing."""

    name: str = "no args tool"
    description: str = "A tool that takes no arguments"
    args_schema: Type[BaseModel] = NoArgsToolSchema

    def _run(self) -> str:
        return "No args result"


class TestConvertCrewaiToolToFunction:
    """Test cases for convert_crewai_tool_to_function."""

    def test_tool_decorated_function_conversion(self):
        """Test conversion of @tool decorated functions."""
        fn = from_crewai_tool(sample_multiply_tool)

        assert fn.__name__ == "sample_multiply_tool"
        assert "Multiply two numbers together" in fn.__doc__

        # Check signature preservation
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["first_number", "second_number"]
        assert sig.parameters["first_number"].annotation is int
        assert sig.parameters["second_number"].annotation is int

        # Test function execution
        result = fn(5, 3)
        assert result == "15"

    def test_tool_decorated_no_args_conversion(self):
        """Test conversion of @tool decorated functions with no arguments."""
        fn = from_crewai_tool(sample_no_args_tool)

        assert fn.__name__ == "sample_no_args_tool"
        assert "A tool that takes no arguments" in fn.__doc__

        # Check signature
        sig = inspect.signature(fn)
        assert len(sig.parameters) == 0

        # Test function execution
        result = fn()
        assert result == "Hello World"

    def test_class_based_tool_with_required_args_conversion(self):
        """Test conversion of class-based tools with required arguments."""
        tool = MultiplyTool()
        fn = from_crewai_tool(tool)

        assert fn.__name__ == "multiply"
        assert "Multiply two numbers" in fn.__doc__

        # Check signature
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["first_number", "second_number"]
        assert sig.parameters["first_number"].annotation is float
        assert sig.parameters["second_number"].annotation is float

        # Both parameters should be required (no defaults)
        assert sig.parameters["first_number"].default == inspect.Parameter.empty
        assert sig.parameters["second_number"].default == inspect.Parameter.empty

        # Test function execution
        result = fn(3.5, 2.0)
        assert result == 7.0

    def test_class_based_tool_with_optional_args_conversion(self):
        """Test conversion of class-based tools with optional arguments."""
        tool = GreetTool()
        fn = from_crewai_tool(tool)

        assert fn.__name__ == "greet"
        assert "Greet someone with a custom message" in fn.__doc__

        # Check signature
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["name", "greeting"]
        assert sig.parameters["name"].annotation is str
        assert sig.parameters["greeting"].annotation is str
        assert sig.parameters["greeting"].default == "Hello"

        # Test function execution with default
        result = fn("Alice")
        assert result == "Hello, Alice!"

        # Test function execution with custom greeting
        result = fn("Bob", "Hi")
        assert result == "Hi, Bob!"

    def test_class_based_tool_no_args_conversion(self):
        """Test conversion of class-based tools with no arguments."""
        tool = NoArgsTool()
        fn = from_crewai_tool(tool)

        assert fn.__name__ == "no_args_tool"
        assert "A tool that takes no arguments" in fn.__doc__

        # Check signature
        sig = inspect.signature(fn)
        assert len(sig.parameters) == 0

        # Test function execution
        result = fn()
        assert result == "No args result"

    def test_name_sanitization(self):
        """Test that tool names with spaces are properly sanitized."""
        tool = NoArgsTool()
        tool.name = "My Custom Tool With Spaces"

        fn = from_crewai_tool(tool)
        assert fn.__name__ == "my_custom_tool_with_spaces"

    def test_name_and_description_override(self):
        """Test that name and description can be overridden."""
        tool = MultiplyTool()

        fn = from_crewai_tool(
            tool, name="custom_multiply", description="Custom multiply description"
        )

        assert fn.__name__ == "custom_multiply"
        assert fn.__doc__ == "Custom multiply description"

    def test_fastmcp_integration(self):
        """Test that converted functions work with FastMCP."""
        # Test @tool decorated function
        fn1 = from_crewai_tool(sample_multiply_tool)
        fast_tool1 = FastTool.from_function(fn1)
        assert fast_tool1.name == "sample_multiply_tool"

        # Test class-based tool with required args
        multiply_tool = MultiplyTool()
        fn2 = from_crewai_tool(multiply_tool)
        fast_tool2 = FastTool.from_function(fn2)
        assert fast_tool2.name == "multiply"

        # Test class-based tool with optional args
        greet_tool = GreetTool()
        fn3 = from_crewai_tool(greet_tool)
        fast_tool3 = FastTool.from_function(fn3)
        assert fast_tool3.name == "greet"

        # Test class-based tool with no args
        no_args_tool = NoArgsTool()
        fn4 = from_crewai_tool(no_args_tool)
        fast_tool4 = FastTool.from_function(fn4)
        assert fast_tool4.name == "no_args_tool"

    def test_error_handling_invalid_tool(self):
        """Test error handling for invalid tools."""

        # Create an object that doesn't have the required methods and isn't callable
        class InvalidTool:
            def __init__(self):
                self.name = "invalid"
                self.description = "invalid"
                # Explicitly don't define func, _run, run, or __call__

        invalid_tool = InvalidTool()

        with pytest.raises(ValueError, match="CrewAI tool must have"):
            from_crewai_tool(invalid_tool)

    def test_fallback_to_run_method(self):
        """Test fallback to run method when func and _run are not available."""
        # Create a tool that only has run method
        tool = Mock()
        tool.name = "fallback tool"
        tool.description = "A fallback tool"
        tool.run = Mock(return_value="fallback result")

        # Ensure it doesn't have func or _run
        del tool.func
        del tool._run
        del tool.args_schema

        fn = from_crewai_tool(tool)

        assert fn.__name__ == "fallback_tool"
        assert fn.__doc__ == "A fallback tool"

        # Test execution
        result = fn("test")
        tool.run.assert_called_once_with("test")
        assert result == "fallback result"

    def test_signature_correctness_for_fastmcp(self):
        """Test that function signatures are correctly preserved for FastMCP."""
        # Test that signatures have proper parameter names, not *args/**kwargs
        multiply_tool = MultiplyTool()
        fn = from_crewai_tool(multiply_tool)

        sig = inspect.signature(fn)

        # Should have named parameters, not generic args
        assert len(sig.parameters) == 2
        param_names = list(sig.parameters.keys())
        assert "first_number" in param_names
        assert "second_number" in param_names

        # Parameters should not be *args or **kwargs
        for param in sig.parameters.values():
            assert param.kind != inspect.Parameter.VAR_POSITIONAL
            assert param.kind != inspect.Parameter.VAR_KEYWORD


class TestCreateFunctionFromSchema:
    """Test cases for _create_function_from_schema helper function."""

    def test_empty_schema(self):
        """Test schema with no fields."""
        mock_run = Mock(return_value="empty result")

        fn = _create_function_from_schema(
            mock_run, NoArgsToolSchema, "test_func", "Test doc"
        )

        assert fn.__name__ == "test_func"
        assert fn.__doc__ == "Test doc"

        sig = inspect.signature(fn)
        assert len(sig.parameters) == 0

        result = fn()
        mock_run.assert_called_once_with()
        assert result == "empty result"

    def test_schema_with_required_fields(self):
        """Test schema with required fields."""
        mock_run = Mock(return_value="multiply result")

        fn = _create_function_from_schema(
            mock_run, MultiplyToolInput, "test_multiply", "Test multiply doc"
        )

        assert fn.__name__ == "test_multiply"
        assert fn.__doc__ == "Test multiply doc"

        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["first_number", "second_number"]
        assert sig.parameters["first_number"].annotation is float
        assert sig.parameters["second_number"].annotation is float

        # Both should be required
        assert sig.parameters["first_number"].default == inspect.Parameter.empty
        assert sig.parameters["second_number"].default == inspect.Parameter.empty

        # Test function execution
        fn(5.0, 3.0)
        mock_run.assert_called_with(first_number=5.0, second_number=3.0)

    def test_schema_with_optional_fields(self):
        """Test schema with optional fields."""
        mock_run = Mock(return_value="greet result")

        fn = _create_function_from_schema(
            mock_run, GreetToolInput, "test_greet", "Test greet doc"
        )

        assert fn.__name__ == "test_greet"
        assert fn.__doc__ == "Test greet doc"

        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["name", "greeting"]
        assert sig.parameters["name"].annotation is str
        assert sig.parameters["greeting"].annotation is str
        assert sig.parameters["greeting"].default == "Hello"

        # Test with both parameters
        fn("Alice", "Hi")
        mock_run.assert_called_with(name="Alice", greeting="Hi")

        # Test with default
        mock_run.reset_mock()
        fn("Bob")
        mock_run.assert_called_with(name="Bob", greeting="Hello")

    def test_parameter_binding_edge_cases(self):
        """Test edge cases for parameter binding."""
        mock_run = Mock(return_value="bound result")

        fn = _create_function_from_schema(
            mock_run, GreetToolInput, "test_func", "Test doc"
        )

        # Test positional arguments
        fn("Alice", "Hi")
        mock_run.assert_called_with(name="Alice", greeting="Hi")

        # Test keyword arguments
        mock_run.reset_mock()
        fn(name="Bob", greeting="Hello")
        mock_run.assert_called_with(name="Bob", greeting="Hello")

        # Test mixed arguments
        mock_run.reset_mock()
        fn("Charlie", greeting="Hey")
        mock_run.assert_called_with(name="Charlie", greeting="Hey")

        # Test with default applied
        mock_run.reset_mock()
        fn("David")
        mock_run.assert_called_with(name="David", greeting="Hello")
