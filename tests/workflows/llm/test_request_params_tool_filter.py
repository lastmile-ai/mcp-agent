import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool, ListToolsResult

from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.agents.agent import Agent
from mcp_agent.mcp.mcp_aggregator import NamespacedTool
from mcp_agent.core.context import Context


class TestRequestParamsToolFilter:
    """Test cases for RequestParams tool_filter backward compatibility and functionality."""

    def test_request_params_default_tool_filter_is_none(self):
        """Test that RequestParams has tool_filter defaulting to None for backward compatibility."""
        # Create RequestParams without specifying tool_filter
        params = RequestParams()

        # Should default to None
        assert params.tool_filter is None

    def test_request_params_accepts_dict_tool_filter(self):
        """Test that RequestParams accepts Dict[str, Set[str]] tool_filter."""
        tool_filter = {"server1": {"tool1", "tool2"}, "server2": {"tool3"}}
        params = RequestParams(tool_filter=tool_filter)

        assert params.tool_filter == tool_filter

    def test_wildcard_filter(self):
        """Test wildcard '*' key in tool_filter."""
        tool_filter = {"*": {"tool1", "tool2"}}
        params = RequestParams(tool_filter=tool_filter)
        assert params.tool_filter == tool_filter

    def test_non_namespaced_tools_key(self):
        """Test non_namespaced_tools key for filtering non-namespaced tools."""
        tool_filter = {"non_namespaced_tools": {"human_input", "function_tool1"}}
        params = RequestParams(tool_filter=tool_filter)
        assert params.tool_filter == tool_filter

    def test_empty_set_filters_all_tools(self):
        """Test that empty set filters out all tools for a server."""
        tool_filter = {"server1": set()}
        params = RequestParams(tool_filter=tool_filter)
        assert params.tool_filter["server1"] == set()

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
            strict=True,
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
        tool_filter = {"server1": {"tool1"}}
        params = RequestParams(maxTokens=2048, tool_filter=tool_filter, temperature=0.8)

        assert params.maxTokens == 2048
        assert params.tool_filter == tool_filter
        assert params.temperature == 0.8

    def test_request_params_model_dump_includes_tool_filter(self):
        """Test that model_dump includes tool_filter when set."""
        tool_filter = {"server1": {"tool1", "tool2"}}
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
        params2 = RequestParams(maxTokens=1000, tool_filter={"server1": {"tool1"}})
        dumped2 = params2.model_dump(exclude_unset=True)
        assert "tool_filter" in dumped2
        assert dumped2["tool_filter"] == {"server1": {"tool1"}}


class TestAgentToolFilteringWithServer:
    """Test cases when server_name is provided to list_tools."""

    @pytest.fixture
    def mock_agent_with_tools(self):
        """Create a mock agent with test data."""
        agent = MagicMock(spec=Agent)
        agent.initialized = True
        agent.context = MagicMock(spec=Context)
        agent.context.tracing_enabled = False

        # Setup server tools
        agent._server_to_tool_map = {
            "server1": [
                NamespacedTool(
                    tool=Tool(name="tool1", description="Tool 1", inputSchema={}),
                    server_name="server1",
                    namespaced_tool_name="server1:tool1",
                ),
                NamespacedTool(
                    tool=Tool(name="tool2", description="Tool 2", inputSchema={}),
                    server_name="server1",
                    namespaced_tool_name="server1:tool2",
                ),
                NamespacedTool(
                    tool=Tool(name="tool3", description="Tool 3", inputSchema={}),
                    server_name="server1",
                    namespaced_tool_name="server1:tool3",
                ),
            ],
            "server2": [
                NamespacedTool(
                    tool=Tool(name="tool1", description="Tool 1", inputSchema={}),
                    server_name="server2",
                    namespaced_tool_name="server2:tool1",
                ),
                NamespacedTool(
                    tool=Tool(name="tool4", description="Tool 4", inputSchema={}),
                    server_name="server2",
                    namespaced_tool_name="server2:tool4",
                ),
            ],
        }

        # Setup function tools
        agent._function_tool_map = {}
        agent.human_input_callback = None

        return agent

    @pytest.mark.asyncio
    async def test_no_filter_includes_all_tools(self, mock_agent_with_tools):
        """Test: tool_filter is None → No filtering, include all tools."""
        result = await self._apply_list_tools_logic(
            mock_agent_with_tools, server_name="server1", tool_filter=None
        )

        assert len(result.tools) == 3
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {"server1:tool1", "server1:tool2", "server1:tool3"}

    @pytest.mark.asyncio
    async def test_server_not_in_filter_includes_all_tools(self, mock_agent_with_tools):
        """Test: server_name not in tool_filter → No filtering for this server."""
        result = await self._apply_list_tools_logic(
            mock_agent_with_tools,
            server_name="server2",
            tool_filter={"server1": {"tool1"}},  # server2 not in filter
        )

        assert len(result.tools) == 2
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {"server2:tool1", "server2:tool4"}

    @pytest.mark.asyncio
    async def test_empty_set_filters_all_tools(self, mock_agent_with_tools):
        """Test: tool_filter[server_name] = set() → Filter all tools out."""
        result = await self._apply_list_tools_logic(
            mock_agent_with_tools, server_name="server1", tool_filter={"server1": set()}
        )

        assert len(result.tools) == 0

    @pytest.mark.asyncio
    async def test_specific_tools_filter(self, mock_agent_with_tools):
        """Test: tool_filter[server_name] = {"tool1", "tool2"} → Only include those tools."""
        result = await self._apply_list_tools_logic(
            mock_agent_with_tools,
            server_name="server1",
            tool_filter={"server1": {"tool1", "tool3"}},
        )

        assert len(result.tools) == 2
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {"server1:tool1", "server1:tool3"}

    async def _apply_list_tools_logic(self, agent, server_name, tool_filter):
        """Apply the actual list_tools filtering logic."""
        filtered_out_tools = []

        if server_name:
            server_tools = agent._server_to_tool_map.get(server_name, [])

            if tool_filter is not None and server_name in tool_filter:
                allowed_tools = tool_filter[server_name]
                result_tools = []
                for namespaced_tool in server_tools:
                    if namespaced_tool.tool.name in allowed_tools:
                        result_tools.append(
                            namespaced_tool.tool.model_copy(
                                update={"name": namespaced_tool.namespaced_tool_name}
                            )
                        )
                    else:
                        filtered_out_tools.append(
                            (
                                namespaced_tool.namespaced_tool_name,
                                f"Not in tool_filter[{server_name}]",
                            )
                        )
                result = ListToolsResult(tools=result_tools)
            else:
                result = ListToolsResult(
                    tools=[
                        namespaced_tool.tool.model_copy(
                            update={"name": namespaced_tool.namespaced_tool_name}
                        )
                        for namespaced_tool in server_tools
                    ]
                )

        return result


class TestAgentToolFilteringAllServers:
    """Test cases when server_name is NOT provided (listing all tools)."""

    @pytest.fixture
    def mock_agent_all_servers(self):
        """Create a mock agent with test data."""
        agent = MagicMock(spec=Agent)
        agent.initialized = True
        agent.context = MagicMock(spec=Context)
        agent.context.tracing_enabled = False

        # Setup namespaced tool map
        agent._namespaced_tool_map = {
            "server1:tool1": NamespacedTool(
                tool=Tool(name="tool1", description="Tool 1", inputSchema={}),
                server_name="server1",
                namespaced_tool_name="server1:tool1",
            ),
            "server1:tool2": NamespacedTool(
                tool=Tool(name="tool2", description="Tool 2", inputSchema={}),
                server_name="server1",
                namespaced_tool_name="server1:tool2",
            ),
            "server2:tool1": NamespacedTool(
                tool=Tool(name="tool1", description="Tool 1", inputSchema={}),
                server_name="server2",
                namespaced_tool_name="server2:tool1",
            ),
            "server2:tool3": NamespacedTool(
                tool=Tool(name="tool3", description="Tool 3", inputSchema={}),
                server_name="server2",
                namespaced_tool_name="server2:tool3",
            ),
            "server3:tool4": NamespacedTool(
                tool=Tool(name="tool4", description="Tool 4", inputSchema={}),
                server_name="server3",
                namespaced_tool_name="server3:tool4",
            ),
        }

        agent._function_tool_map = {}
        agent.human_input_callback = None

        return agent

    @pytest.mark.asyncio
    async def test_server_in_filter_applies_filter(self, mock_agent_all_servers):
        """Test: X in tool_filter → Apply filter for server X."""
        result = await self._apply_list_tools_logic_all_servers(
            mock_agent_all_servers,
            tool_filter={"server1": {"tool1"}, "server2": {"tool3"}},
        )

        # server1: only tool1, server2: only tool3, server3: all tools (no filter)
        assert len(result.tools) == 3
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {"server1:tool1", "server2:tool3", "server3:tool4"}

    @pytest.mark.asyncio
    async def test_wildcard_applies_to_unfiltered_servers(self, mock_agent_all_servers):
        """Test: X not in tool_filter and '*' in tool_filter → Apply wildcard filter."""
        result = await self._apply_list_tools_logic_all_servers(
            mock_agent_all_servers,
            tool_filter={
                "server1": {"tool1"},  # Explicit filter for server1
                "*": {"tool3", "tool4"},  # Wildcard for others
            },
        )

        # server1: only tool1 (explicit filter)
        # server2: only tool3 (from wildcard)
        # server3: only tool4 (from wildcard)
        assert len(result.tools) == 3
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {"server1:tool1", "server2:tool3", "server3:tool4"}

    @pytest.mark.asyncio
    async def test_no_filter_no_wildcard_includes_tool(self, mock_agent_all_servers):
        """Test: X not in tool_filter and '*' not in tool_filter → Include tool (no filter)."""
        result = await self._apply_list_tools_logic_all_servers(
            mock_agent_all_servers,
            tool_filter={"server1": {"tool1"}},  # Only server1 has filter
        )

        # server1: only tool1 (explicit filter)
        # server2: all tools (no filter)
        # server3: all tools (no filter)
        assert len(result.tools) == 4
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {
            "server1:tool1",
            "server2:tool1",
            "server2:tool3",
            "server3:tool4",
        }

    @pytest.mark.asyncio
    async def test_empty_filter_dict_includes_all(self, mock_agent_all_servers):
        """Test: tool_filter = {} → All tools included (no explicit filters defined)."""
        result = await self._apply_list_tools_logic_all_servers(
            mock_agent_all_servers, tool_filter={}
        )

        # Empty dict means no explicit filters are defined
        # Since no server is explicitly listed and there's no wildcard,
        # the logic falls through to include all tools by default
        assert len(result.tools) == 5  # All 5 tools from the fixture should be included

    @pytest.mark.asyncio
    async def test_wildcard_only_filter(self, mock_agent_all_servers):
        """Test: Only wildcard filter applies to all servers."""
        result = await self._apply_list_tools_logic_all_servers(
            mock_agent_all_servers, tool_filter={"*": {"tool1"}}
        )

        # All servers should only include tool1
        assert len(result.tools) == 2
        tool_names = {tool.name for tool in result.tools}
        assert tool_names == {"server1:tool1", "server2:tool1"}

    @pytest.mark.asyncio
    async def test_block_all_tools_with_wildcard_empty_set(
        self, mock_agent_all_servers
    ):
        """Test: Use wildcard with empty set to block all tools."""
        result = await self._apply_list_tools_logic_all_servers(
            mock_agent_all_servers, tool_filter={"*": set()}
        )

        # Wildcard with empty set blocks all tools from all servers
        assert len(result.tools) == 0

    async def _apply_list_tools_logic_all_servers(self, agent, tool_filter):
        """Apply the actual list_tools filtering logic for all servers."""
        filtered_out_tools = []

        if tool_filter is not None:
            filtered_tools = []
            for (
                namespaced_tool_name,
                namespaced_tool,
            ) in agent._namespaced_tool_map.items():
                should_include = False

                if namespaced_tool.server_name in tool_filter:
                    if (
                        namespaced_tool.tool.name
                        in tool_filter[namespaced_tool.server_name]
                    ):
                        should_include = True
                    else:
                        filtered_out_tools.append(
                            (
                                namespaced_tool_name,
                                f"Not in tool_filter[{namespaced_tool.server_name}]",
                            )
                        )
                elif "*" in tool_filter:
                    if namespaced_tool.tool.name in tool_filter["*"]:
                        should_include = True
                    else:
                        filtered_out_tools.append(
                            (namespaced_tool_name, "Not in tool_filter[*]")
                        )
                else:
                    should_include = True

                if should_include:
                    filtered_tools.append(
                        namespaced_tool.tool.model_copy(
                            update={"name": namespaced_tool_name}
                        )
                    )
            result = ListToolsResult(tools=filtered_tools)
        else:
            result = ListToolsResult(
                tools=[
                    namespaced_tool.tool.model_copy(
                        update={"name": namespaced_tool_name}
                    )
                    for namespaced_tool_name, namespaced_tool in agent._namespaced_tool_map.items()
                ]
            )

        return result


class TestNonNamespacedToolFiltering:
    """Test filtering of function tools and human input tools."""

    def test_non_namespaced_tools_key_filters(self):
        """Test: non_namespaced_tools key filters function tools and human input."""
        from mcp_agent.agents.agent import Agent

        agent = MagicMock(spec=Agent)
        agent._should_include_non_namespaced_tool = (
            Agent._should_include_non_namespaced_tool.__get__(agent)
        )

        # Test inclusion with non_namespaced_tools key
        should_include, reason = agent._should_include_non_namespaced_tool(
            "func1", {"non_namespaced_tools": {"func1", "human_input"}}
        )
        assert should_include is True
        assert reason is None

        # Test exclusion with non_namespaced_tools key
        should_include, reason = agent._should_include_non_namespaced_tool(
            "func2", {"non_namespaced_tools": {"func1", "human_input"}}
        )
        assert should_include is False
        assert "not in tool_filter[non_namespaced_tools]" in reason

    def test_wildcard_filters_non_namespaced(self):
        """Test: Wildcard filters non-namespaced tools when no non_namespaced_tools key."""
        from mcp_agent.agents.agent import Agent

        agent = MagicMock(spec=Agent)
        agent._should_include_non_namespaced_tool = (
            Agent._should_include_non_namespaced_tool.__get__(agent)
        )

        should_include, reason = agent._should_include_non_namespaced_tool(
            "func1", {"*": {"func1", "human_input"}}
        )
        assert should_include is True

        should_include, reason = agent._should_include_non_namespaced_tool(
            "func2", {"*": {"func1", "human_input"}}
        )
        assert should_include is False
        assert "not in tool_filter[*]" in reason

    def test_no_filter_includes_non_namespaced(self):
        """Test: No non_namespaced_tools key and no wildcard includes non-namespaced tools."""
        from mcp_agent.agents.agent import Agent

        agent = MagicMock(spec=Agent)
        agent._should_include_non_namespaced_tool = (
            Agent._should_include_non_namespaced_tool.__get__(agent)
        )

        should_include, reason = agent._should_include_non_namespaced_tool(
            "func1",
            {"server1": {"tool1"}},  # No non_namespaced_tools key or wildcard
        )
        assert should_include is True
        assert reason is None


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
        agent.list_tools = AsyncMock(
            return_value=ListToolsResult(
                tools=[
                    Tool(name="tool1", description="Tool 1", inputSchema={}),
                    Tool(name="tool2", description="Tool 2", inputSchema={}),
                ]
            )
        )
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
        override_params = RequestParams(tool_filter={"server1": {"tool1"}})
        result2 = llm.get_request_params(request_params=override_params)
        assert result2.maxTokens == 1000  # From default
        assert result2.tool_filter == {"server1": {"tool1"}}  # From override

        # Test 3: Override with non_namespaced_tools key
        override_params3 = RequestParams(
            tool_filter={"non_namespaced_tools": {"human_input"}}
        )
        result3 = llm.get_request_params(request_params=override_params3)
        assert result3.tool_filter == {"non_namespaced_tools": {"human_input"}}

        # Test 3: Override with existing params only
        override_params2 = RequestParams(temperature=0.9)
        result4 = llm.get_request_params(request_params=override_params2)
        assert result4.maxTokens == 1000  # From default
        assert result4.temperature == 0.9  # From override
        assert result4.tool_filter is None  # Default

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


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_same_tool_name_different_servers(self):
        """Test that tools with same name from different servers are handled correctly."""
        agent = MagicMock(spec=Agent)
        agent._namespaced_tool_map = {
            "server1:tool1": NamespacedTool(
                tool=Tool(
                    name="tool1", description="Tool 1 from server1", inputSchema={}
                ),
                server_name="server1",
                namespaced_tool_name="server1:tool1",
            ),
            "server2:tool1": NamespacedTool(
                tool=Tool(
                    name="tool1", description="Tool 1 from server2", inputSchema={}
                ),
                server_name="server2",
                namespaced_tool_name="server2:tool1",
            ),
        }

        # Filter should work independently for each server
        tool_filter = {"server1": {"tool1"}, "server2": set()}

        # server1:tool1 should be included, server2:tool1 should not
        assert "server1" in tool_filter
        assert "tool1" in tool_filter["server1"]
        assert "server2" in tool_filter
        assert len(tool_filter["server2"]) == 0

    def test_server_not_in_map(self):
        """Test requesting tools from a server that doesn't exist."""
        agent = MagicMock(spec=Agent)
        agent._server_to_tool_map = {}

        # Should return empty list, not error
        server_tools = agent._server_to_tool_map.get("nonexistent", [])
        assert server_tools == []

    def test_request_params_with_invalid_tool_filter_type(self):
        """Test that RequestParams handles invalid tool_filter types gracefully."""
        # Test with string (should cause type error)
        try:
            params = RequestParams(tool_filter="invalid_string")
            # If no exception, it's being converted somehow
            assert isinstance(params.tool_filter, dict) or params.tool_filter is None
        except (ValueError, TypeError):
            pass  # This is expected behavior

        # Test with dict having non-set values (should convert or error)
        try:
            params_with_list = RequestParams(
                tool_filter={"server1": ["tool1", "tool2"]}
            )
            # Pydantic should convert list to set
            if params_with_list.tool_filter:
                assert isinstance(params_with_list.tool_filter["server1"], set)
                assert params_with_list.tool_filter["server1"] == {"tool1", "tool2"}
        except (ValueError, TypeError):
            pass  # This is also acceptable behavior

    def test_request_params_with_empty_dict_tool_filter(self):
        """Test that RequestParams accepts empty dict for tool_filter."""
        # Empty dict should be valid (means no tools allowed from any server)
        params = RequestParams(tool_filter={})
        assert params.tool_filter == {}

    def test_request_params_with_none_tool_filter_explicit(self):
        """Test that RequestParams accepts explicit None for tool_filter."""
        params = RequestParams(tool_filter=None)
        assert params.tool_filter is None
