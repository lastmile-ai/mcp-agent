import pytest
from unittest.mock import MagicMock

from mcp_agent.config import LMStudioSettings
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_lm_studio import LMStudioAugmentedLLM


class TestLMStudioAugmentedLLM:
    """
    Tests for the LMStudioAugmentedLLM class.
    """

    @pytest.fixture
    def mock_llm(self, mock_context):
        """
        Creates a mock LM Studio LLM instance with common mocks set up.
        """
        mock_context.config.lm_studio = LMStudioSettings(
            default_model=None,
            base_url="http://localhost:1234/v1",
        )

        llm = LMStudioAugmentedLLM(name="test", context=mock_context)
        llm.history = MagicMock()
        llm.history.get = MagicMock(return_value=[])
        llm.history.set = MagicMock()

        return llm

    def test_initialization(self, mock_llm):
        """
        Test that LMStudioAugmentedLLM initializes correctly.
        """
        assert mock_llm.name == "test"
        assert mock_llm.provider == "LM Studio"

    def test_get_provider_config(self, mock_context):
        """
        Test that get_provider_config returns the lm_studio config.
        """
        mock_context.config.lm_studio = LMStudioSettings(
            base_url="http://localhost:1234/v1",
        )

        config = LMStudioAugmentedLLM.get_provider_config(mock_context)

        assert config is not None
        assert config.base_url == "http://localhost:1234/v1"

    def test_default_settings(self):
        """
        Test that LMStudioSettings has correct defaults.
        """
        settings = LMStudioSettings()

        assert settings.base_url == "http://localhost:1234/v1"
        assert settings.default_model is None

    def test_api_key_injection(self, mock_context):
        """
        Test that api_key is injected automatically during initialization.
        """
        mock_context.config.lm_studio = LMStudioSettings(
            base_url="http://localhost:1234/v1",
        )

        llm = LMStudioAugmentedLLM(name="test", context=mock_context)

        assert hasattr(llm.context.config.lm_studio, "api_key")
        assert llm.context.config.lm_studio.api_key == "lm-studio"

    @pytest.mark.asyncio
    async def test_select_model_uses_config_default(self, mock_context):
        """
        Test that select_model returns the config's default_model when set.
        """
        mock_context.config.lm_studio = LMStudioSettings(
            default_model="deepseek/deepseek-r1-distill-qwen-14b",
            base_url="http://localhost:1234/v1",
        )

        llm = LMStudioAugmentedLLM(name="test", context=mock_context)

        model = await llm.select_model()

        assert model == "deepseek/deepseek-r1-distill-qwen-14b"

    @pytest.mark.asyncio
    async def test_select_model_request_params_override(self, mock_context):
        """
        Test that select_model prioritizes request_params.model over config.
        """
        mock_context.config.lm_studio = LMStudioSettings(
            default_model="deepseek/deepseek-r1-distill-qwen-14b",
            base_url="http://localhost:1234/v1",
        )

        llm = LMStudioAugmentedLLM(name="test", context=mock_context)

        # Request params should override config
        request_params = RequestParams(model="custom-model")
        model = await llm.select_model(request_params)

        assert model == "custom-model"

    @pytest.mark.asyncio
    async def test_select_model_no_config_default(self, mock_context):
        """
        Test that select_model falls back to parent when no config default_model.
        """

        mock_context.config.lm_studio = LMStudioSettings(
            default_model=None,
            base_url="http://localhost:1234/v1",
        )

        llm = LMStudioAugmentedLLM(name="test", context=mock_context)

        # Mock the parent's select_model to verify fallback behavior
        original_select = LMStudioAugmentedLLM.__bases__[0].select_model
        parent_called = False

        async def mock_parent_select(self, request_params=None):
            nonlocal parent_called
            parent_called = True
            return "benchmark-model"

        LMStudioAugmentedLLM.__bases__[0].select_model = mock_parent_select

        try:
            model = await llm.select_model()
            assert parent_called, (
                "Parent's select_model should be called when no config default"
            )
            assert model == "benchmark-model"
        finally:
            # Restore original
            LMStudioAugmentedLLM.__bases__[0].select_model = original_select
