import pytest
from unittest.mock import MagicMock

from mcp_agent.config import LMStudioSettings
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
