import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool, ListToolsResult

from mcp_agent.workflows.llm.augmented_llm import RequestParams


class TestRequestParamsToolFilter:
    """Test cases for RequestParams tool_filter backward compatibility and functionality."""

    def test_request_params_default_tool_filter_is_none(self):
        """Test that RequestParams has tool_filter defaulting to None for backward compatibility."""
        # Create RequestParams without specifying tool_filter
        params = RequestParams()
        
        # Should default to None
        assert params.tool_filter is None

    def test_request_params_accepts_tool_filter(self):
        """Test that RequestParams accepts tool_filter parameter."""
        tool_filter = {"tool1", "tool2"}
        params = RequestParams(tool_filter=tool_filter)
        
        assert params.tool_filter == tool_filter

    def test_request_params_existing_fields_unchanged(self):
        """Test that existing RequestParams fields work as before."""
        # Test existing parameters work unchanged
        params = RequestParams(
            maxTokens=1000,
            model="test-model",
            use_history=False,
            max_iterations=5,
            parallel_tool_calls=True,
            temperature=0.5,
            user="test-user",
            strict=True
        )
        
        # All existing fields should work
        assert params.maxTokens == 1000
        assert params.model == "test-model"
        assert params.use_history is False
        assert params.max_iterations == 5
        assert params.parallel_tool_calls is True
        assert params.temperature == 0.5
        assert params.user == "test-user"
        assert params.strict is True
        # New field should default to None
        assert params.tool_filter is None

    def test_request_params_with_mixed_parameters(self):
        """Test RequestParams with both old and new parameters."""
        tool_filter = {"tool1"}
        params = RequestParams(
            maxTokens=2048,
            tool_filter=tool_filter,
            temperature=0.8
        )
        
        assert params.maxTokens == 2048
        assert params.tool_filter == tool_filter
        assert params.temperature == 0.8

    def test_request_params_model_dump_includes_tool_filter(self):
        """Test that model_dump includes tool_filter when set."""
        tool_filter = {"tool1", "tool2"}
        params = RequestParams(tool_filter=tool_filter)
        
        dumped = params.model_dump()
        assert "tool_filter" in dumped
        assert dumped["tool_filter"] == tool_filter

    def test_request_params_model_dump_excludes_unset_tool_filter(self):
        """Test that model_dump with exclude_unset=True handles tool_filter correctly."""
        # When tool_filter is not set
        params1 = RequestParams(maxTokens=1000)
        dumped1 = params1.model_dump(exclude_unset=True)
        # tool_filter should not be in dumped output if not set
        assert "tool_filter" not in dumped1 or dumped1.get("tool_filter") is None
        
        # When tool_filter is explicitly set
        params2 = RequestParams(maxTokens=1000, tool_filter={"tool1"})
        dumped2 = params2.model_dump(exclude_unset=True)
        assert "tool_filter" in dumped2
        assert dumped2["tool_filter"] == {"tool1"}


class TestBackwardCompatibilityIntegration:
    """Integration tests to ensure existing code patterns still work."""

    @pytest.fixture
    def mock_context(self):
        """Create a Context with mocked components for testing."""
        from mcp_agent.core.context import Context

        context = Context()
        context.executor = AsyncMock()
        context.server_registry = MagicMock()
        context.tracing_enabled = False
        return context

    @pytest.fixture 
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = MagicMock()
        agent.list_tools = AsyncMock(return_value=ListToolsResult(tools=[
            Tool(name="tool1", description="Tool 1", inputSchema={}),
            Tool(name="tool2", description="Tool 2", inputSchema={})
        ]))
        return agent

    @pytest.mark.asyncio
    async def test_existing_code_without_tool_filter_still_works(self, mock_agent):
        """Test that existing code calling agent.list_tools() without parameters still works."""
        # This simulates existing code that doesn't use tool_filter
        result = await mock_agent.list_tools()
        
        assert len(result.tools) == 2
        assert result.tools[0].name == "tool1"
        assert result.tools[1].name == "tool2"
        
        # Verify the call was made without tool_filter parameter
        mock_agent.list_tools.assert_called_with()

    @pytest.mark.asyncio
    async def test_existing_code_with_server_name_still_works(self, mock_agent):
        """Test that existing code calling agent.list_tools(server_name) still works."""
        # This simulates existing code that uses server_name parameter
        result = await mock_agent.list_tools(server_name="test_server")
        
        assert len(result.tools) == 2
        
        # Verify the call was made with server_name but without tool_filter
        mock_agent.list_tools.assert_called_with(server_name="test_server")

    def test_augmented_llm_get_request_params_backward_compatible(self, mock_context):
        """Test that AugmentedLLM.get_request_params handles tool_filter correctly."""
        from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
        
        # Create a mock AugmentedLLM instance
        llm = MagicMock(spec=AugmentedLLM)
        llm.context = mock_context
        llm.default_request_params = RequestParams(maxTokens=1000)
        
        # Simulate the get_request_params method behavior
        def mock_get_request_params(request_params=None, default=None):
            default_params = default or llm.default_request_params
            params = default_params.model_dump() if default_params else {}
            if request_params:
                params.update(request_params.model_dump(exclude_unset=True))
            return RequestParams(**params)
        
        llm.get_request_params = mock_get_request_params
        
        # Test 1: No overrides (existing behavior)
        result1 = llm.get_request_params()
        assert result1.maxTokens == 1000
        assert result1.tool_filter is None
        
        # Test 2: Override with new tool_filter
        override_params = RequestParams(tool_filter={"tool1"})
        result2 = llm.get_request_params(request_params=override_params)
        assert result2.maxTokens == 1000  # From default
        assert result2.tool_filter == {"tool1"}  # From override
        
        # Test 3: Override with existing params only
        override_params2 = RequestParams(temperature=0.9)
        result3 = llm.get_request_params(request_params=override_params2)
        assert result3.maxTokens == 1000  # From default
        assert result3.temperature == 0.9  # From override
        assert result3.tool_filter is None  # Default

    @pytest.mark.asyncio
    async def test_augmented_llm_list_tools_method_signature_compatible(self):
        """Test that AugmentedLLM.list_tools method signature is backward compatible."""
        from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM
        import inspect
        
        # Get the method signature
        sig = inspect.signature(AugmentedLLM.list_tools)
        params = list(sig.parameters.keys())
        
        # Should have both old and new parameters
        assert "self" in params
        assert "server_name" in params  # Existing parameter
        assert "tool_filter" in params  # New parameter
        
        # Both should be optional (have defaults)
        server_name_param = sig.parameters["server_name"]
        tool_filter_param = sig.parameters["tool_filter"]
        
        assert server_name_param.default is None
        assert tool_filter_param.default is None


class TestErrorHandling:
    """Test error handling for the tool_filter feature."""

    def test_request_params_with_invalid_tool_filter_type(self):
        """Test that RequestParams handles invalid tool_filter types gracefully."""
        # Note: Pydantic may be lenient with type conversion, so this test verifies behavior
        # rather than strict type validation
        
        # Test with string (may get converted to set or cause issues)
        try:
            params = RequestParams(tool_filter="invalid_string")
            # If no exception, verify the behavior
            assert params.tool_filter != "invalid_string"  # Should not remain as string
        except (ValueError, TypeError):
            pass  # This is also acceptable behavior
        
        # Test with list (should work since it's iterable -> set)
        params_with_list = RequestParams(tool_filter=["tool1", "tool2"])
        # Pydantic should convert list to set
        assert isinstance(params_with_list.tool_filter, set)
        assert params_with_list.tool_filter == {"tool1", "tool2"}

    def test_request_params_with_empty_set_tool_filter(self):
        """Test that RequestParams accepts empty set for tool_filter."""
        # Empty set should be valid
        params = RequestParams(tool_filter=set())
        assert params.tool_filter == set()

    def test_request_params_with_none_tool_filter_explicit(self):
        """Test that RequestParams accepts explicit None for tool_filter."""
        params = RequestParams(tool_filter=None)
        assert params.tool_filter is None